"""Worker: turns Analysis Jobs into Analysis Results.

Run with ``python -m analysis_service.worker``.
"""

import asyncio
import logging
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import httpx
from faststream import AckPolicy, FastStream
from faststream.rabbit import QueueType, RabbitQueue
from faststream.rabbit.annotations import RabbitMessage
from faststream.rabbit.schemas import Channel

from analysis_service.detector import Detect, Detection, load_detector
from analysis_service.images import ImageFailure, decode_image, fetch_image
from analysis_service.messages import AnalysisJob, AnalysisResult, Box, ResultError
from analysis_service.queues import (
    confirming_broker,
    declare_queue,
    publish_confirmed,
)
from analysis_service.settings import WorkerSettings

MODEL = "yolox-s"
# Wikimedia answers 403 to the default python-httpx User-Agent; it wants
# one that names the app and a contact: https://w.wiki/4wJS
USER_AGENT = (
    "people-counter/0.1 (+https://github.com/NoratanS/ZaawansowaneProgramowanie)"
)

logger = logging.getLogger(__name__)


def build_worker(settings: WorkerSettings, detect: Detect) -> FastStream:
    jobs_queue = settings.jobs_queue
    results_queue = settings.results_queue
    broker = confirming_broker(settings.rabbitmq_url)
    # No per-operation timeout: fetch_image enforces the total limit itself,
    # and httpx's 5 s default would cut it short when the limit is longer.
    http = httpx.AsyncClient(timeout=None, headers={"User-Agent": USER_AGENT})
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
                allowed_hosts=settings.image_allowed_hosts,
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
            await publish_confirmed(
                broker, result, queue=results_queue.name, message_id=str(job.job_id)
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

    def clip(value: float, limit: int) -> int:
        return round(min(max(value, 0), limit))

    left = clip(detection.x, width)
    top = clip(detection.y, height)
    right = clip(detection.x + detection.width, width)
    bottom = clip(detection.y + detection.height, height)
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


def cpu_limit(cpu_max: str, host_cpus: int) -> int:
    """Whole CPUs a container may use, from cgroup v2 ``cpu.max`` text.

    ``cpu_max`` is ``"<quota> <period>"`` or ``"max <period>"``. Text in any
    other shape, such as ``""`` for no cgroup v2 file, leaves only ``host_cpus``.
    """
    try:
        quota, period = cpu_max.split()
        cpus = math.ceil(int(quota) / int(period))
    except ValueError, ZeroDivisionError:
        return host_cpus
    return min(host_cpus, cpus)


def _container_cpus() -> int:
    """CPUs this process may use: its affinity, capped by the cgroup quota."""
    try:
        cpu_max = Path("/sys/fs/cgroup/cpu.max").read_text()
    except OSError:
        cpu_max = ""
    return cpu_limit(cpu_max, os.process_cpu_count() or 1)


def main() -> None:
    settings = WorkerSettings()
    logging.basicConfig(level=settings.log_level)
    # Without the cap OpenCV starts a thread per host core, and replicas
    # with a CPU quota fight over them.
    cv2.setNumThreads(_container_cpus())
    detect = load_detector(settings.model_path)
    asyncio.run(build_worker(settings, detect).run())


if __name__ == "__main__":
    main()
