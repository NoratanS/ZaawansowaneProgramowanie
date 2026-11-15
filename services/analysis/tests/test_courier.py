import asyncio
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import aio_pika
import pytest
from werkzeug import Response

from analysis_service.courier import build_courier
from analysis_service.queues import RESULTS_QUEUE
from analysis_service.settings import CourierSettings
import result_cases

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
def courier_for(rabbitmq_url, clean_broker, httpserver, jwt_keys):
    """Run a Courier aimed at the stub Results Service until the block ends."""

    @asynccontextmanager
    async def run_courier(results_service_url=None, **overrides):
        settings = CourierSettings(
            rabbitmq_url=rabbitmq_url,
            results_service_url=results_service_url or httpserver.url_for("/"),
            jwt_private_key=jwt_keys.private,
            **FAST | overrides,
        )
        async with build_courier(settings):
            yield

    return run_courier


@pytest.fixture
def publish(channel):
    """Queue a message on ``analysis-results`` the way the Worker does."""

    async def publish_body(body: bytes, message_id: str):
        await channel.default_exchange.publish(
            aio_pika.Message(
                body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=message_id,
            ),
            routing_key=RESULTS_QUEUE,
        )

    return publish_body


@pytest.fixture
def publish_result(publish):
    """Queue a valid succeeded Analysis Result; return its id and body."""

    async def publish_one():
        job_id = str(uuid4())
        case = result_cases.load("succeeded-with-zero-people")
        result = case.body | {"job_id": job_id}
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


async def test_the_put_carries_a_results_service_bearer_token(
    courier_for, script, publish_result, requests_made, read_token
):
    script()

    async with courier_for():
        await publish_result()
        [request] = await requests_made(1)

    scheme, token = request.headers["Authorization"].split(" ")
    assert scheme == "Bearer"
    claims = read_token(token, "results-service")
    assert claims["exp"] - claims["iat"] == 300


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
    assert await drain(RESULTS_QUEUE) == []
    assert await drain(f"{RESULTS_QUEUE}.dlq") == []


async def test_a_transient_failure_is_retried_then_delivered(
    courier_for, script, publish_result, requests_made, drain, courier_logs
):
    # A PUT past the delivery timeout; the unit tests cover the status table.
    script(stall)

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
    assert await drain(RESULTS_QUEUE) == []
    assert await drain(f"{RESULTS_QUEUE}.dlq") == []
