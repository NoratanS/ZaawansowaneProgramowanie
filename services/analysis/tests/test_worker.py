import asyncio
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import aio_pika
import pytest
from werkzeug import Response

from fakes import FakeDetector, png

from analysis_service.detector import Detection
from analysis_service.queues import JOBS_QUEUE, RESULTS_QUEUE
from analysis_service.settings import WorkerSettings
from analysis_service.worker import build_worker

pytestmark = pytest.mark.integration

# Small delays and limits so retries and dead-lettering happen in milliseconds.
FAST = {
    "jobs_queue_retry_min_seconds": 0.05,
    "jobs_queue_retry_max_seconds": 0.2,
    "image_fetch_timeout_seconds": 0.2,
    "image_max_bytes": 10_000,
    # The image origin fake listens on localhost, which the guard would refuse.
    "image_allowed_hosts": frozenset({"localhost"}),
}


@pytest.fixture
def worker_for(rabbitmq_url, clean_broker, upload_settings):
    """Run a Worker with a fake detector until the block ends."""

    @asynccontextmanager
    async def run_worker(detect, **overrides):
        settings = WorkerSettings(
            rabbitmq_url=rabbitmq_url, **upload_settings | FAST | overrides
        )
        async with build_worker(settings, detect):
            yield

    return run_worker


@pytest.fixture
def submit(channel):
    """Queue an Analysis Job the way the Analysis Service does."""

    async def publish_job(image_url):
        job = {
            "job_id": str(uuid4()),
            "image_url": image_url,
            "requested_at": datetime.now(UTC).isoformat(),
        }
        await channel.default_exchange.publish(
            aio_pika.Message(
                json.dumps(job).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=job["job_id"],
            ),
            routing_key=JOBS_QUEUE,
        )
        return job

    return publish_job


async def test_a_job_becomes_a_succeeded_result(
    worker_for, submit, next_message, drain, httpserver
):
    httpserver.expect_request("/people.png").respond_with_data(
        png(width=40, height=30), content_type="image/png"
    )
    # Clipping and rounding are unit-tested in test_analyse.py.
    detect = FakeDetector([Detection(x=1, y=2, width=8, height=9, confidence=0.9)])
    before = datetime.now(UTC)

    async with worker_for(detect):
        job = await submit(httpserver.url_for("/people.png"))
        message = await next_message(RESULTS_QUEUE)

    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert message.message_id == job["job_id"]
    result = json.loads(message.body)
    analyzed_at = datetime.fromisoformat(result.pop("analyzed_at"))
    assert analyzed_at.utcoffset() == timedelta(0)
    assert before <= analyzed_at <= datetime.now(UTC)
    requested_at = datetime.fromisoformat(result.pop("requested_at"))
    assert requested_at == datetime.fromisoformat(job["requested_at"])
    assert result == {
        "job_id": job["job_id"],
        "image_url": job["image_url"],
        "status": "succeeded",
        "person_count": 1,
        "detections": [{"x": 1, "y": 2, "width": 8, "height": 9, "confidence": 0.9}],
        "error": None,
        "model": "yolox-s",
    }
    [image] = detect.images
    assert image.shape == (30, 40, 3)
    # The Worker has stopped, so an unacked job would be back in the queue.
    assert await drain(JOBS_QUEUE) == []


async def test_an_internal_url_becomes_a_forbidden_result_without_a_request(
    worker_for, submit, next_message, drain, httpserver
):
    httpserver.expect_request("/people.png").respond_with_data(png(8, 8))
    detect = FakeDetector()

    async with worker_for(detect, image_allowed_hosts=frozenset()):
        job = await submit(httpserver.url_for("/people.png"))
        message = await next_message(RESULTS_QUEUE)
        # Long enough for several redeliveries at the 50 ms retry delay.
        await asyncio.sleep(0.6)

    result = json.loads(message.body)
    assert result["job_id"] == job["job_id"]
    assert result["status"] == "failed"
    assert result["error"]["code"] == "image_url_forbidden"
    assert httpserver.log == []
    assert detect.images == []
    assert await drain(RESULTS_QUEUE) == []
    assert await drain(JOBS_QUEUE) == []


async def test_the_image_request_names_the_app_in_its_user_agent(
    worker_for, submit, next_message, httpserver
):
    # Wikimedia answers 403 to the default python-httpx User-Agent.
    httpserver.expect_request("/people.png").respond_with_data(png(8, 8))

    async with worker_for(FakeDetector()):
        await submit(httpserver.url_for("/people.png"))
        await next_message(RESULTS_QUEUE)

    [(request, _)] = httpserver.log
    assert request.headers["User-Agent"] == (
        "people-counter/0.1 (+https://github.com/NoratanS/ZaawansowaneProgramowanie)"
    )


def slow_first_byte(request):
    time.sleep(5.5)  # past httpx's 5 s default timeout, within the 8 s limit
    return Response(png(4, 4), content_type="image/png")


async def test_the_fetch_limit_is_not_cut_short_by_httpx_defaults(
    worker_for, submit, next_message, httpserver
):
    httpserver.expect_request("/slow.png").respond_with_handler(slow_first_byte)

    async with worker_for(FakeDetector(), image_fetch_timeout_seconds=8):
        await submit(httpserver.url_for("/slow.png"))
        message = await next_message(RESULTS_QUEUE, timeout=10)

    assert json.loads(message.body)["status"] == "succeeded"


async def test_a_job_that_keeps_crashing_is_dead_lettered_after_the_limit(
    worker_for, submit, next_message, drain, httpserver
):
    httpserver.expect_request("/people.png").respond_with_data(png(8, 8))
    detect = FakeDetector(error=RuntimeError("detector exploded"))

    async with worker_for(detect, jobs_queue_delivery_limit=3):
        job = await submit(httpserver.url_for("/people.png"))
        dead = await next_message(f"{JOBS_QUEUE}.dlq")
        # Give a stray extra delivery the chance to show up.
        await asyncio.sleep(0.3)

    assert json.loads(dead.body)["job_id"] == job["job_id"]
    # RabbitMQ's x-delivery-limit counts failed returns, so the job is tried
    # once and retried 3 times (the spec's ~12 s window is 2 + 4 + 6 s).
    assert len(detect.images) == 1 + 3
    assert await drain(RESULTS_QUEUE) == []
    assert await drain(JOBS_QUEUE) == []


@pytest.mark.parametrize("results_queue", ["refusing", "missing"])
async def test_a_job_is_not_acked_when_its_result_is_not_confirmed(
    worker_for, submit, next_message, drain, channel, httpserver, results_queue
):
    httpserver.expect_request("/people.png").respond_with_data(png(8, 8))
    detect = FakeDetector()

    async with worker_for(detect, jobs_queue_delivery_limit=2):
        await channel.queue_delete(RESULTS_QUEUE)
        if results_queue == "refusing":
            # A queue that refuses every message, so the broker nacks.
            await channel.declare_queue(
                RESULTS_QUEUE,
                durable=True,
                arguments={"x-max-length": 0, "x-overflow": "reject-publish"},
            )
        job = await submit(httpserver.url_for("/people.png"))
        dead = await next_message(f"{JOBS_QUEUE}.dlq")

    assert json.loads(dead.body)["job_id"] == job["job_id"]
    assert len(detect.images) == 1 + 2
    assert await drain(JOBS_QUEUE) == []


def job_lines(caplog):
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "analysis_service.worker" and r.levelno == logging.INFO
    ]


async def test_each_job_logs_one_info_line(
    worker_for, submit, next_message, httpserver, caplog
):
    caplog.set_level(logging.INFO, logger="analysis_service.worker")
    httpserver.expect_request("/people.png").respond_with_data(png(8, 8))
    httpserver.expect_request("/missing").respond_with_data("gone", status=404)
    one_person = FakeDetector([Detection(x=1, y=1, width=4, height=4, confidence=0.8)])

    async with worker_for(one_person):
        good = await submit(httpserver.url_for("/people.png"))
        await next_message(RESULTS_QUEUE)
        bad = await submit(httpserver.url_for("/missing"))
        await next_message(RESULTS_QUEUE)

    succeeded, failed = job_lines(caplog)
    assert re.fullmatch(
        rf"job_id={good['job_id']} status=succeeded person_count=1 duration_ms=\d+",
        succeeded,
    )
    assert re.fullmatch(
        rf"job_id={bad['job_id']} status=failed error=image_unreachable"
        r" person_count=None duration_ms=\d+",
        failed,
    )
