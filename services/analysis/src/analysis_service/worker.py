"""Worker: turns Analysis Jobs into Analysis Results.

Run with ``python -m analysis_service.worker``.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from faststream import AckPolicy, FastStream
from faststream.rabbit import QueueType, RabbitBroker, RabbitQueue
from faststream.rabbit.annotations import RabbitMessage
from faststream.rabbit.schemas import Channel

from analysis_service.detector import Detect, Detection, detect_nobody
from analysis_service.images import ImageFailure, decode_image, fetch_image
from analysis_service.messages import AnalysisJob, AnalysisResult, Box, ResultError
from analysis_service.queues import declare_queue
from analysis_service.settings import WorkerSettings

MODEL = "yolox-s"
# How long the Worker waits for the broker to confirm a Result.
PUBLISH_TIMEOUT_SECONDS = 5.0

logger = logging.getLogger(__name__)


def build_worker(settings: WorkerSettings, detect: Detect) -> FastStream:
    jobs_queue = settings.jobs_queue
    results_queue = settings.results_queue
    # on_return_raises makes an unroutable Result a failed publish.
    broker = RabbitBroker(
        settings.rabbitmq_url, default_channel=Channel(on_return_raises=True)
    )
    # No per-operation timeout: fetch_image enforces the total limit itself,
    # and httpx's 5 s default would cut it short when the limit is longer.
    http = httpx.AsyncClient(timeout=None)
    app = FastStream(broker)

    @app.on_startup
    async def declare_queues() -> None:
        # Declare before the subscriber starts consuming from analysis-jobs.
        await broker.connect()
        await declare_queue(broker, jobs_queue)
        await declare_queue(broker, results_queue)

    @app.after_shutdown
    async def close_http() -> None:
        await http.aclose()

    async def analyse(job: AnalysisJob) -> AnalysisResult:
        def result(**outcome: Any) -> AnalysisResult:
            return AnalysisResult(
                job_id=job.job_id,
                image_url=job.image_url,
                model=MODEL,
                requested_at=job.requested_at,
                analyzed_at=datetime.now(UTC),
                **outcome,
            )

        try:
            data = await fetch_image(
                http,
                str(job.image_url),
                timeout_seconds=settings.image_fetch_timeout_seconds,
                max_bytes=settings.image_max_bytes,
            )
            image = await asyncio.to_thread(decode_image, data)
        except ImageFailure as failure:
            # Bad input is final: a failed Result, never a retry.
            return result(
                status="failed",
                error=ResultError(code=failure.code, message=failure.message),
            )
        height, width = image.shape[:2]
        found = await asyncio.to_thread(detect, image)
        boxes = [box for d in found if (box := _to_box(d, width, height))]
        return result(status="succeeded", person_count=len(boxes), detections=boxes)

    @broker.subscriber(
        RabbitQueue(jobs_queue.name, queue_type=QueueType.QUORUM, declare=False),
        channel=Channel(prefetch_count=settings.worker_prefetch),
        ack_policy=AckPolicy.MANUAL,
    )
    async def handle_job(message: RabbitMessage) -> None:
        started = time.perf_counter()
        try:
            job = AnalysisJob.model_validate_json(message.body)
            result = await analyse(job)
            # Waits for the publisher confirm; a nack or return raises.
            await broker.publish(
                result,
                queue=results_queue.name,
                persist=True,
                message_id=str(job.job_id),
                timeout=PUBLISH_TIMEOUT_SECONDS,
            )
        except Exception:
            # reject, not nack: only reject counts toward the delivery limit,
            # so a job that keeps failing ends up in the DLQ.
            logger.exception("job_id=%s requeued after an error", message.message_id)
            await message.reject(requeue=True)
            return
        await message.ack()
        _log_outcome(result, started)

    return app


def _to_box(detection: Detection, width: int, height: int) -> Box | None:
    """Clip a detection to the image and round it; ``None`` if nothing is left."""
    left = round(min(max(detection.x, 0), width))
    top = round(min(max(detection.y, 0), height))
    right = round(min(max(detection.x + detection.width, 0), width))
    bottom = round(min(max(detection.y + detection.height, 0), height))
    if right <= left or bottom <= top:
        return None
    return Box(
        x=left,
        y=top,
        width=right - left,
        height=bottom - top,
        confidence=detection.confidence,
    )


def _log_outcome(result: AnalysisResult, started: float) -> None:
    status = result.status
    if result.error is not None:
        status += f" error={result.error.code}"
    duration_ms = round((time.perf_counter() - started) * 1000)
    logger.info(
        "job_id=%s status=%s person_count=%s duration_ms=%d",
        result.job_id,
        status,
        result.person_count,
        duration_ms,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(build_worker(WorkerSettings(), detect_nobody).run())


if __name__ == "__main__":
    main()
