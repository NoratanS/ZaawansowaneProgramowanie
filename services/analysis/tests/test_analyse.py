import threading
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from analysis_service.detector import Detection
from analysis_service.images import ImageFailure
from analysis_service.messages import AnalysisJob
from analysis_service.worker import analyse
from fakes import FakeDetector, png

pytestmark = pytest.mark.unit

URL = "http://images.example/people.png"


def serving(data):
    """An in-memory ``load_image`` that answers every URL with ``data``."""

    async def load_image(image_url):
        return data

    return load_image


def failing(code, message):
    """An in-memory ``load_image`` that can't load any URL."""

    async def load_image(image_url):
        raise ImageFailure(code, message)

    return load_image


def job_for(image_url=URL):
    return AnalysisJob(
        job_id=uuid4(), image_url=image_url, requested_at=datetime.now(UTC)
    )


async def test_a_job_becomes_a_succeeded_result_with_clipped_rounded_boxes():
    job = job_for()
    detect = FakeDetector(
        [
            # Sticks out left and bottom: clipped to the image, then rounded.
            Detection(x=-5.4, y=2.6, width=20.0, height=40.0, confidence=0.9),
            Detection(x=10.2, y=5.0, width=8.6, height=10.4, confidence=0.6),
        ]
    )

    result = await analyse(job, serving(png(width=40, height=30)), detect)

    assert result.model_dump(exclude={"analyzed_at"}) == {
        "job_id": job.job_id,
        "image_url": job.image_url,
        "status": "succeeded",
        "person_count": 2,
        "detections": [
            {"x": 0, "y": 3, "width": 15, "height": 27, "confidence": 0.9},
            {"x": 10, "y": 5, "width": 9, "height": 10, "confidence": 0.6},
        ],
        "error": None,
        "model": "yolox-s",
        "requested_at": job.requested_at,
    }
    [image] = detect.images
    assert image.shape == (30, 40, 3)


async def boxes_for(*detections, width=40, height=30):
    """The boxes ``analyse`` reports for these detections on a blank image."""
    result = await analyse(
        job_for(), serving(png(width, height)), FakeDetector(detections)
    )
    assert result.person_count == len(result.detections)
    return [box.model_dump() for box in result.detections]


OUTSIDE = {
    "left": Detection(x=-10.0, y=5.0, width=5.0, height=5.0, confidence=0.9),
    "right": Detection(x=50.0, y=5.0, width=5.0, height=5.0, confidence=0.9),
    "above": Detection(x=5.0, y=-20.0, width=5.0, height=10.0, confidence=0.9),
    "below": Detection(x=5.0, y=31.0, width=5.0, height=5.0, confidence=0.9),
    # Inside, but under half a pixel wide: rounds to zero width.
    "sliver": Detection(x=10.2, y=5.0, width=0.2, height=5.0, confidence=0.9),
}


@pytest.mark.parametrize("outside", OUTSIDE.values(), ids=OUTSIDE.keys())
async def test_boxes_clipped_away_entirely_are_dropped(outside):
    kept = Detection(x=1.0, y=1.0, width=4.0, height=4.0, confidence=0.8)

    assert await boxes_for(outside, kept) == [
        {"x": 1, "y": 1, "width": 4, "height": 4, "confidence": 0.8}
    ]


async def test_a_box_bigger_than_the_image_is_clipped_to_the_whole_image():
    huge = Detection(x=-5.0, y=-5.0, width=100.0, height=100.0, confidence=0.7)

    assert await boxes_for(huge) == [
        {"x": 0, "y": 0, "width": 40, "height": 30, "confidence": 0.7}
    ]


async def test_no_detections_is_a_count_of_zero():
    assert await boxes_for() == []


CODES = ["image_unreachable", "not_an_image", "image_too_large", "image_url_forbidden"]


@pytest.mark.parametrize("code", CODES)
async def test_an_image_failure_becomes_a_failed_result_with_its_code(code):
    job = job_for()
    detect = FakeDetector()

    result = await analyse(job, failing(code, "the image is no good"), detect)

    assert result.model_dump(exclude={"analyzed_at"}) == {
        "job_id": job.job_id,
        "image_url": job.image_url,
        "status": "failed",
        "person_count": None,
        "detections": None,
        "error": {"code": code, "message": "the image is no good"},
        "model": "yolox-s",
        "requested_at": job.requested_at,
    }
    assert detect.images == []


@pytest.mark.parametrize("data", [b"hello", b""], ids=["text", "empty"])
async def test_bytes_that_dont_decode_become_a_failed_result(data):
    detect = FakeDetector()

    result = await analyse(job_for(), serving(data), detect)

    assert result.status == "failed"
    assert result.error.code == "not_an_image"
    assert detect.images == []


class ThreadRecordingBytes(bytes):
    """Bytes that note which thread reads their buffer, as decoding does."""

    def __buffer__(self, flags):
        self.threads.append(threading.current_thread())
        return super().__buffer__(flags)


async def test_decoding_runs_off_the_event_loop():
    data = ThreadRecordingBytes(png(8, 8))
    data.threads = []

    result = await analyse(job_for(), serving(data), FakeDetector())

    assert result.status == "succeeded"
    # A blocking decode on the loop thread would stall heartbeats and other jobs.
    assert data.threads
    assert threading.current_thread() not in data.threads


async def test_analyzed_at_is_the_time_of_the_analysis():
    before = datetime.now(UTC)

    result = await analyse(job_for(), serving(png(8, 8)), FakeDetector())

    assert before <= result.analyzed_at <= datetime.now(UTC)
