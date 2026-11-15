import logging
import re
from datetime import UTC, datetime
from uuid import uuid4

import pydantic
import pytest

from fakes import FakeDetector, FakeJobs, png

from analysis_service.detector import Detection
from analysis_service.images import ImageFailure
from analysis_service.messages import AnalysisJob
from analysis_service.queues import Action, NotQueued
from analysis_service.worker import handle_job

pytestmark = pytest.mark.unit

URL = "http://images.example/people.png"
WORKER = "worker-1"


async def load_png(image_url):
    return png(8, 8)


async def load_nothing(image_url):
    raise ImageFailure("image_unreachable", "the image server answered 404")


def body_for(image_url=URL):
    job = AnalysisJob(
        job_id=uuid4(), image_url=image_url, requested_at=datetime.now(UTC)
    )
    return job, job.model_dump_json().encode()


async def test_a_succeeded_job_publishes_its_result_and_is_acked():
    job, body = body_for()
    results = FakeJobs()
    detect = FakeDetector([Detection(x=1, y=1, width=4, height=4, confidence=0.8)])

    action = await handle_job(body, load_png, detect, results, worker=WORKER)

    assert action is Action.ACK
    [result] = results.published
    assert result.job_id == job.job_id
    assert result.status == "succeeded"
    assert result.person_count == 1
    assert result.worker == WORKER
    assert results.message_ids == [str(job.job_id)]


async def test_a_malformed_body_raises_and_publishes_nothing():
    results = FakeJobs()

    with pytest.raises(pydantic.ValidationError):
        await handle_job(b"not json", load_png, FakeDetector(), results, worker=WORKER)

    assert results.published == []


async def test_a_result_that_is_not_queued_raises():
    _, body = body_for()
    results = FakeJobs()
    results.refusing = True

    with pytest.raises(NotQueued):
        await handle_job(body, load_png, FakeDetector(), results, worker=WORKER)


def job_lines(caplog):
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "analysis_service.worker" and r.levelno == logging.INFO
    ]


async def test_each_job_logs_one_info_line(caplog):
    caplog.set_level(logging.INFO, logger="analysis_service.worker")
    one_person = FakeDetector([Detection(x=1, y=1, width=4, height=4, confidence=0.8)])
    good, good_body = body_for()
    bad, bad_body = body_for("http://images.example/missing")
    results = FakeJobs()

    await handle_job(good_body, load_png, one_person, results, worker=WORKER)
    await handle_job(bad_body, load_nothing, one_person, results, worker=WORKER)

    succeeded, failed = job_lines(caplog)
    assert re.fullmatch(
        rf"job_id={good.job_id} worker={re.escape(WORKER)} status=succeeded"
        r" person_count=1 duration_ms=\d+",
        succeeded,
    )
    assert re.fullmatch(
        rf"job_id={bad.job_id} worker={re.escape(WORKER)}"
        r" status=failed error=image_unreachable"
        r" person_count=None duration_ms=\d+",
        failed,
    )
