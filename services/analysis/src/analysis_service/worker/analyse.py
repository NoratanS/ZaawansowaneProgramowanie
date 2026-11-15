"""Analysing one Analysis Job: load its image, count the people, log the outcome."""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from analysis_service.messages import AnalysisJob, AnalysisResult, ResultError
from analysis_service.queues import Action, Publisher
from analysis_service.worker.detector import Detect
from analysis_service.worker.images import ImageFailure, LoadImage, decode_image

MODEL = "yolox-s"

logger = logging.getLogger(__name__)


async def analyse(
    job: AnalysisJob, load_image: LoadImage, detect: Detect, *, worker: str
) -> AnalysisResult:
    """Count the people in the job's image; the Result names ``worker``.

    An image that can't be loaded or decoded gives a failed Result; any
    other error raises.
    """

    def result(**outcome: Any) -> AnalysisResult:
        return AnalysisResult(
            job_id=job.job_id,
            image_url=job.image_url,
            model=MODEL,
            worker=worker,
            requested_at=job.requested_at,
            analyzed_at=datetime.now(UTC),
            **outcome,
        )

    try:
        data = await load_image(str(job.image_url))
        image = await asyncio.to_thread(decode_image, data)
    except ImageFailure as failure:
        # Bad input is final: a failed Result, never a retry.
        return result(
            status="failed",
            error=ResultError(code=failure.code, message=failure.message),
        )
    boxes = await asyncio.to_thread(detect, image)
    return result(status="succeeded", person_count=len(boxes), detections=boxes)


async def handle_job(
    body: bytes,
    load_image: LoadImage,
    detect: Detect,
    results: Publisher,
    *,
    worker: str,
) -> Action:
    """Analyse one job body, publish its Result, log one line and ACK.

    Errors raise: the queue module retries the job, then dead-letters it.
    """
    started = time.perf_counter()
    job = AnalysisJob.model_validate_json(body)
    result = await analyse(job, load_image, detect, worker=worker)
    await results.publish(result, message_id=str(job.job_id))
    _log_outcome(result, started)
    return Action.ACK


def _log_outcome(result: AnalysisResult, started: float) -> None:
    status = result.status
    if result.error is not None:
        status += f" error={result.error.code}"
    duration_ms = round((time.perf_counter() - started) * 1000)
    logger.info(
        "job_id=%s worker=%s status=%s person_count=%s duration_ms=%d",
        result.job_id,
        result.worker,
        status,
        result.person_count,
        duration_ms,
    )
