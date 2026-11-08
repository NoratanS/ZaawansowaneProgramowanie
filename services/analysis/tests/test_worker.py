import asyncio
import json
import logging
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import aio_pika
import cv2
import numpy as np
import pytest
from werkzeug import Response

from analysis_service import worker
from analysis_service.detector import Detection
from analysis_service.settings import WorkerSettings
from analysis_service.uploads import UPLOADS_BUCKET
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


def png(width, height):
    ok, encoded = cv2.imencode(".png", np.zeros((height, width, 3), dtype=np.uint8))
    assert ok
    return encoded.tobytes()


class FakeDetector:
    """Stands in for YOLOX: returns canned detections and records its calls."""

    def __init__(self, detections=(), error=None):
        self.detections = list(detections)
        self.error = error
        self.images = []

    def __call__(self, image):
        self.images.append(image)
        if self.error is not None:
            raise self.error
        return self.detections


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
            routing_key="analysis-jobs",
        )
        return job

    return publish_job


async def test_a_job_becomes_a_succeeded_result(
    worker_for, submit, next_message, drain, httpserver
):
    httpserver.expect_request("/people.png").respond_with_data(
        png(width=40, height=30), content_type="image/png"
    )
    detect = FakeDetector(
        [
            # Sticks out left and bottom: clipped to the image, then rounded.
            Detection(x=-5.4, y=2.6, width=20.0, height=40.0, confidence=0.9),
            Detection(x=10.2, y=5.0, width=8.6, height=10.4, confidence=0.6),
        ]
    )
    before = datetime.now(UTC)

    async with worker_for(detect):
        job = await submit(httpserver.url_for("/people.png"))
        message = await next_message("analysis-results")

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
        "person_count": 2,
        "detections": [
            {"x": 0, "y": 3, "width": 15, "height": 27, "confidence": 0.9},
            {"x": 10, "y": 5, "width": 9, "height": 10, "confidence": 0.6},
        ],
        "error": None,
        "model": "yolox-s",
    }
    [image] = detect.images
    assert image.shape == (30, 40, 3)
    # The Worker has stopped, so an unacked job would be back in the queue.
    assert await drain("analysis-jobs") == []


def stalled(request):
    time.sleep(0.5)  # past the 0.2 s fetch limit
    return Response(png(4, 4), content_type="image/png")


def endless_body(request):
    # Chunked, so there is no Content-Length to reject up front.
    return Response((b"x" * 1000 for _ in range(30)), content_type="image/png")


IMAGE_FAILURES = {
    "404": (lambda r: Response("gone", status=404), "image_unreachable"),
    "500": (lambda r: Response("oops", status=500), "image_unreachable"),
    "slow": (stalled, "image_unreachable"),
    "oversize": (lambda r: Response(b"x" * 20_000), "image_too_large"),
    "lying-stream": (endless_body, "image_too_large"),
    "text": (lambda r: Response("hello", content_type="text/plain"), "not_an_image"),
}


@pytest.mark.parametrize(
    ("handler", "code"), IMAGE_FAILURES.values(), ids=IMAGE_FAILURES.keys()
)
async def test_a_bad_image_becomes_a_failed_result_without_retry(
    worker_for, submit, next_message, drain, httpserver, handler, code
):
    httpserver.expect_request("/image").respond_with_handler(handler)
    detect = FakeDetector()

    async with worker_for(detect):
        job = await submit(httpserver.url_for("/image"))
        message = await next_message("analysis-results")
        # Long enough for several redeliveries at the 50 ms retry delay.
        await asyncio.sleep(0.6)

    result = json.loads(message.body)
    assert result["job_id"] == job["job_id"]
    assert result["status"] == "failed"
    assert result["error"]["code"] == code
    assert result["error"]["message"]
    assert result["person_count"] is None
    assert result["detections"] is None
    assert result["model"] == "yolox-s"
    assert len(httpserver.log) == 1
    assert detect.images == []
    assert await drain("analysis-results") == []
    assert await drain("analysis-jobs") == []


async def test_a_refused_connection_becomes_image_unreachable(
    worker_for, submit, next_message
):
    async with worker_for(FakeDetector()):
        # Nothing listens on port 1.
        await submit("http://localhost:1/people.png")
        message = await next_message("analysis-results")

    assert json.loads(message.body)["error"]["code"] == "image_unreachable"


async def test_an_internal_url_becomes_a_forbidden_result_without_a_request(
    worker_for, submit, next_message, drain, httpserver
):
    httpserver.expect_request("/people.png").respond_with_data(png(8, 8))
    detect = FakeDetector()

    async with worker_for(detect, image_allowed_hosts=frozenset()):
        job = await submit(httpserver.url_for("/people.png"))
        message = await next_message("analysis-results")
        # Long enough for several redeliveries at the 50 ms retry delay.
        await asyncio.sleep(0.6)

    result = json.loads(message.body)
    assert result["job_id"] == job["job_id"]
    assert result["status"] == "failed"
    assert result["error"]["code"] == "image_url_forbidden"
    assert httpserver.log == []
    assert detect.images == []
    assert await drain("analysis-results") == []
    assert await drain("analysis-jobs") == []


async def test_the_image_request_names_the_app_in_its_user_agent(
    worker_for, submit, next_message, httpserver
):
    # Wikimedia answers 403 to the default python-httpx User-Agent.
    httpserver.expect_request("/people.png").respond_with_data(png(8, 8))

    async with worker_for(FakeDetector()):
        await submit(httpserver.url_for("/people.png"))
        await next_message("analysis-results")

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
        message = await next_message("analysis-results", timeout=10)

    assert json.loads(message.body)["status"] == "succeeded"


async def test_decoding_runs_off_the_event_loop(
    worker_for, submit, next_message, httpserver, monkeypatch
):
    httpserver.expect_request("/people.png").respond_with_data(png(8, 8))
    threads = []

    def recording_decode(data):
        threads.append(threading.current_thread())
        return decode_image(data)

    decode_image = worker.decode_image
    monkeypatch.setattr(worker, "decode_image", recording_decode)

    async with worker_for(FakeDetector()):
        await submit(httpserver.url_for("/people.png"))
        message = await next_message("analysis-results")

    assert json.loads(message.body)["status"] == "succeeded"
    # A blocking decode on the loop thread would stall heartbeats and other jobs.
    assert threads and threading.main_thread() not in threads


async def test_a_job_that_keeps_crashing_is_dead_lettered_after_the_limit(
    worker_for, submit, next_message, drain, httpserver
):
    httpserver.expect_request("/people.png").respond_with_data(png(8, 8))
    detect = FakeDetector(error=RuntimeError("detector exploded"))

    async with worker_for(detect, jobs_queue_delivery_limit=3):
        job = await submit(httpserver.url_for("/people.png"))
        dead = await next_message("analysis-jobs.dlq")
        # Give a stray extra delivery the chance to show up.
        await asyncio.sleep(0.3)

    assert json.loads(dead.body)["job_id"] == job["job_id"]
    # RabbitMQ's x-delivery-limit counts failed returns, so the job is tried
    # once and retried 3 times (the spec's ~12 s window is 2 + 4 + 6 s).
    assert len(detect.images) == 1 + 3
    assert await drain("analysis-results") == []
    assert await drain("analysis-jobs") == []


@pytest.mark.parametrize("results_queue", ["refusing", "missing"])
async def test_a_job_is_not_acked_when_its_result_is_not_confirmed(
    worker_for, submit, next_message, drain, channel, httpserver, results_queue
):
    httpserver.expect_request("/people.png").respond_with_data(png(8, 8))
    detect = FakeDetector()

    async with worker_for(detect, jobs_queue_delivery_limit=2):
        await channel.queue_delete("analysis-results")
        if results_queue == "refusing":
            # A queue that refuses every message, so the broker nacks.
            await channel.declare_queue(
                "analysis-results",
                durable=True,
                arguments={"x-max-length": 0, "x-overflow": "reject-publish"},
            )
        job = await submit(httpserver.url_for("/people.png"))
        dead = await next_message("analysis-jobs.dlq")

    assert json.loads(dead.body)["job_id"] == job["job_id"]
    assert len(detect.images) == 1 + 2
    assert await drain("analysis-jobs") == []


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
        await next_message("analysis-results")
        bad = await submit(httpserver.url_for("/missing"))
        await next_message("analysis-results")

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


@pytest.fixture
async def stored_upload(s3_client, upload_settings):
    """Put an object in the upload store as the API would; return its URL."""
    await s3_client.create_bucket(Bucket=UPLOADS_BUCKET)
    uploads_url = f"{upload_settings['analysis_public_url']}/uploads"

    async def put(data, content_type="image/png"):
        upload_id = str(uuid4())
        await s3_client.put_object(
            Bucket=UPLOADS_BUCKET, Key=upload_id, Body=data, ContentType=content_type
        )
        return f"{uploads_url}/{upload_id}"

    return put


async def test_an_uploaded_photo_is_read_from_the_store_not_fetched(
    worker_for, submit, next_message, stored_upload, monkeypatch
):
    def no_fetch(*args, **kwargs):
        raise AssertionError("an upload must not be fetched over HTTP")

    monkeypatch.setattr(worker, "fetch_image", no_fetch)
    detect = FakeDetector([Detection(x=1, y=1, width=4, height=4, confidence=0.8)])

    async with worker_for(detect):
        job = await submit(await stored_upload(png(width=40, height=30)))
        message = await next_message("analysis-results")

    result = json.loads(message.body)
    assert result["job_id"] == job["job_id"]
    assert result["image_url"] == job["image_url"]
    assert result["status"] == "succeeded"
    assert result["person_count"] == 1
    [image] = detect.images
    assert image.shape == (30, 40, 3)


UPLOAD_FAILURES = {
    "text": (b"hello", "not_an_image"),
    "oversize": (b"x" * 20_000, "image_too_large"),
}


@pytest.mark.parametrize(
    ("data", "code"), UPLOAD_FAILURES.values(), ids=UPLOAD_FAILURES.keys()
)
async def test_a_bad_upload_becomes_a_failed_result(
    worker_for, submit, next_message, stored_upload, data, code
):
    async with worker_for(FakeDetector()):
        await submit(await stored_upload(data, content_type="text/plain"))
        message = await next_message("analysis-results")

    assert json.loads(message.body)["error"]["code"] == code


@pytest.mark.parametrize("upload_id", [uuid4(), "not-an-id"], ids=["missing", "bad-id"])
async def test_an_upload_that_isnt_there_is_unreachable(
    worker_for, submit, next_message, stored_upload, upload_settings, drain, upload_id
):
    # stored_upload is only here for its bucket: the object is what's missing.
    async with worker_for(FakeDetector()):
        await submit(f"{upload_settings['analysis_public_url']}/uploads/{upload_id}")
        message = await next_message("analysis-results")
        # Long enough for a redelivery at the 50 ms retry delay to show up.
        await asyncio.sleep(0.3)

    assert json.loads(message.body)["error"]["code"] == "image_unreachable"
    assert await drain("analysis-jobs") == []
