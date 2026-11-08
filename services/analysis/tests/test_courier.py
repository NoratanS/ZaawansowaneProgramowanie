import asyncio
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import aio_pika
import pytest
from werkzeug import Response

from analysis_service.courier import build_courier
from analysis_service.settings import CourierSettings

pytestmark = pytest.mark.integration

# Small delays, limit and timeout so retries and dead-lettering take milliseconds.
FAST = {
    "results_queue_retry_min_seconds": 0.05,
    "results_queue_retry_max_seconds": 0.2,
    "results_queue_delivery_limit": 3,
    "delivery_timeout_seconds": 0.2,
}
RESULTS = re.compile(r"^/results/.+$")


@pytest.fixture
def courier_for(rabbitmq_url, clean_broker, httpserver):
    """Run a Courier aimed at the stub Results Service until the block ends."""

    @asynccontextmanager
    async def run_courier(results_service_url=None, **overrides):
        settings = CourierSettings(
            rabbitmq_url=rabbitmq_url,
            results_service_url=results_service_url or httpserver.url_for("/"),
            **FAST | overrides,
        )
        async with build_courier(settings):
            yield

    return run_courier


@pytest.fixture
def publish(channel):
    """Queue a message on ``analysis-results`` the way the Worker does."""

    async def publish_body(body: bytes, message_id: str | None = None):
        await channel.default_exchange.publish(
            aio_pika.Message(
                body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=message_id,
            ),
            routing_key="analysis-results",
        )

    return publish_body


@pytest.fixture
def publish_result(publish):
    """Queue a valid succeeded Analysis Result; return its id and body."""

    async def publish_one():
        job_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        result = {
            "job_id": job_id,
            "image_url": "https://images.example/people.jpg",
            "status": "succeeded",
            "person_count": 0,
            "detections": [],
            "error": None,
            "model": "yolox-s",
            "requested_at": now,
            "analyzed_at": now,
        }
        body = json.dumps(result).encode()
        await publish(body, message_id=job_id)
        return job_id, body

    return publish_one


@pytest.fixture
def script(httpserver):
    """Make the stub answer PUTs with ``handlers`` in order, then 201 forever."""

    def answer(*handlers):
        for handler in handlers:
            httpserver.expect_oneshot_request(
                RESULTS, method="PUT"
            ).respond_with_handler(handler)
        httpserver.expect_request(RESULTS, method="PUT").respond_with_handler(
            respond(201)
        )

    return answer


@pytest.fixture
def requests_made(httpserver):
    """Wait until the stub has seen ``count`` requests, then return them all."""

    async def wait_for(count, timeout=5):
        async with asyncio.timeout(timeout):
            while len(httpserver.log) < count:
                await asyncio.sleep(0.02)
        return [request for request, _ in httpserver.log]

    return wait_for


@pytest.fixture
def courier_logs(caplog):
    caplog.set_level(logging.INFO, logger="analysis_service.courier")

    def lines(level):
        return [
            r.getMessage()
            for r in caplog.records
            if r.name == "analysis_service.courier" and r.levelno == level
        ]

    return lines


def respond(status):
    return lambda request: Response("{}", status=status)


def stall(request):
    # Past the 0.2 s delivery timeout, but short: the stub serves one request
    # at a time, so the retry (~50 ms after the timeout) waits behind this one.
    time.sleep(0.3)
    return Response("{}", status=201)


async def settle():
    """Long enough for several redeliveries at the 50 ms retry delay."""
    await asyncio.sleep(0.6)


@pytest.mark.parametrize("status", [200, 201])
async def test_a_stored_result_is_acked(
    courier_for, script, publish_result, requests_made, drain, status
):
    script(respond(status))

    async with courier_for():
        job_id, body = await publish_result()
        await requests_made(1)
        await settle()

    [request] = await requests_made(1)
    assert request.method == "PUT"
    assert request.path == f"/results/{job_id}"
    assert request.headers["Content-Type"] == "application/json"
    assert request.get_data() == body
    # The Courier has stopped, so an unacked message would be back in the queue.
    assert await drain("analysis-results") == []
    assert await drain("analysis-results.dlq") == []


TRANSIENT = {
    "502": respond(502),
    "503": respond(503),
    "522": respond(522),
    "524": respond(524),
    "408": respond(408),
    "429": respond(429),
    "timeout": stall,
}


@pytest.mark.parametrize("handler", TRANSIENT.values(), ids=TRANSIENT.keys())
async def test_a_transient_failure_is_retried_then_delivered(
    courier_for, script, publish_result, requests_made, drain, courier_logs, handler
):
    script(handler)

    async with courier_for():
        job_id, body = await publish_result()
        await requests_made(2)
        await settle()

    first, second = await requests_made(2)
    assert first.get_data() == second.get_data() == body
    [warning] = courier_logs(logging.WARNING)
    assert warning.startswith(f"job_id={job_id} retrying cause=")
    assert warning.endswith(" x-delivery-count=0")
    assert courier_logs(logging.ERROR) == []
    assert await drain("analysis-results") == []
    assert await drain("analysis-results.dlq") == []


async def test_503_503_201_ends_delivered(
    courier_for, script, publish_result, requests_made, drain, courier_logs
):
    script(respond(503), respond(503))

    async with courier_for():
        job_id, _ = await publish_result()
        await requests_made(3)
        await settle()

    assert len(await requests_made(3)) == 3
    assert courier_logs(logging.WARNING) == [
        f"job_id={job_id} retrying cause=HTTP 503 x-delivery-count=0",
        f"job_id={job_id} retrying cause=HTTP 503 x-delivery-count=1",
    ]
    assert courier_logs(logging.INFO) == [f"job_id={job_id} delivered status=201"]
    assert await drain("analysis-results") == []
    assert await drain("analysis-results.dlq") == []


async def test_a_result_that_never_lands_is_dead_lettered_after_the_limit(
    courier_for, httpserver, publish_result, next_message, drain
):
    httpserver.expect_request(RESULTS, method="PUT").respond_with_handler(respond(503))

    async with courier_for(results_queue_delivery_limit=3):
        job_id, body = await publish_result()
        dead = await next_message("analysis-results.dlq")
        await settle()

    assert dead.body == body
    # x-delivery-limit counts failed returns: one try plus 3 retries.
    assert len(httpserver.log) == 1 + 3
    assert await drain("analysis-results") == []


async def test_a_closed_port_is_retried_until_the_dlq(
    courier_for, publish_result, next_message, courier_logs
):
    # Nothing listens on port 1.
    async with courier_for(results_service_url="http://127.0.0.1:1"):
        job_id, body = await publish_result()
        dead = await next_message("analysis-results.dlq")

    assert dead.body == body
    warnings = courier_logs(logging.WARNING)
    assert len(warnings) == 1 + 3
    assert all(w.startswith(f"job_id={job_id} retrying cause=") for w in warnings)


@pytest.mark.parametrize("status", [401, 422])
async def test_a_rejected_result_goes_straight_to_the_dlq(
    courier_for, script, publish_result, next_message, drain, courier_logs, status
):
    script(respond(status))

    async with courier_for():
        job_id, body = await publish_result()
        dead = await next_message("analysis-results.dlq")
        await settle()

    assert dead.body == body
    assert courier_logs(logging.ERROR) == [
        f"job_id={job_id} dead-lettered cause=HTTP {status}"
    ]
    assert courier_logs(logging.WARNING) == []
    assert await drain("analysis-results") == []


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b"{}", b'{"job_id": "../health"}', b'{"job_id": 7}'],
    ids=["not-json", "not-an-object", "no-job-id", "path-in-job-id", "int-job-id"],
)
async def test_a_message_without_a_job_id_is_dead_lettered_unsent(
    courier_for, httpserver, publish, next_message, courier_logs, body
):
    async with courier_for():
        await publish(body)
        dead = await next_message("analysis-results.dlq")

    assert dead.body == body
    assert httpserver.log == []
    [error] = courier_logs(logging.ERROR)
    assert "dead-lettered" in error
