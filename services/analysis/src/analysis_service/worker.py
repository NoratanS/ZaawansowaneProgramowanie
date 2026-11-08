"""Worker: turns Analysis Jobs into Analysis Results.

Run with ``python -m analysis_service.worker``.
"""

import asyncio
import logging
import math
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import httpx
from faststream import FastStream

from analysis_service.detector import Detect, Detection, load_detector
from analysis_service.images import ImageFailure, decode_image, fetch_image
from analysis_service.messages import AnalysisJob, AnalysisResult, Box, ResultError
from analysis_service.queues import Action, Queue, confirming_broker
from analysis_service.settings import WorkerSettings
from analysis_service.uploads import UploadStore, open_store, upload_id_in

MODEL = "yolox-s"
# Wikimedia answers 403 to the default python-httpx User-Agent; it wants
# one that names the app and a contact: https://w.wiki/4wJS
USER_AGENT = (
    "people-counter/0.1 (+https://github.com/NoratanS/ZaawansowaneProgramowanie)"
)

logger = logging.getLogger(__name__)


LoadImage = Callable[[str], Awaitable[bytes | bytearray]]
"""Reads the image at a URL; raises ``ImageFailure`` if it can't."""


async def analyse(
    job: AnalysisJob, load_image: LoadImage, detect: Detect
) -> AnalysisResult:
    """Count the people in the job's image.

    An image that can't be loaded or decoded gives a failed Result; any
    other error raises.
    """

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
        data = await load_image(str(job.image_url))
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


class _ImageLoader:
    """The Worker's ``load_image``: uploads from the store, other URLs over HTTP.

    Call ``open`` at startup, before the first image is loaded.
    """

    def __init__(self, settings: WorkerSettings) -> None:
        self._settings = settings
        # No per-operation timeout: fetch_image enforces the total limit itself,
        # and httpx's 5 s default would cut it short when the limit is longer.
        self._http = httpx.AsyncClient(timeout=None, headers={"User-Agent": USER_AGENT})
        self._resources = AsyncExitStack()
        self._resources.push_async_callback(self._http.aclose)
        self._store: UploadStore | None = None

    async def open(self) -> None:
        # The API creates the bucket, not the Worker.
        self._store = await self._resources.enter_async_context(
            open_store(self._settings)
        )

    async def aclose(self) -> None:
        await self._resources.aclose()

    async def __call__(self, image_url: str) -> bytearray:
        settings = self._settings
        # Uploads are read by key, so the SSRF guard has nothing to check.
        if (
            upload_id := upload_id_in(image_url, settings.uploads_base_url)
        ) is not None:
            return await self._store.read_image(upload_id, settings.image_max_bytes)
        return await fetch_image(
            self._http,
            image_url,
            timeout_seconds=settings.image_fetch_timeout_seconds,
            max_bytes=settings.image_max_bytes,
            allowed_hosts=settings.image_allowed_hosts,
        )


def build_worker(settings: WorkerSettings, detect: Detect) -> FastStream:
    broker = confirming_broker(settings.rabbitmq_url)
    jobs = Queue(broker, settings.jobs_queue)
    results = Queue(broker, settings.results_queue)
    load_image = _ImageLoader(settings)
    app = FastStream(broker)

    @app.on_startup
    async def start() -> None:
        await load_image.open()
        # Declare before the subscriber starts consuming from analysis-jobs.
        await broker.connect()
        await jobs.declare()
        await results.declare()

    @app.after_shutdown
    async def close() -> None:
        await load_image.aclose()

    # Errors raise: the queue module retries the job, then dead-letters it.
    async def handle_job(
        body: bytes, headers: Mapping[str, Any], message_id: str | None
    ) -> Action:
        started = time.perf_counter()
        job = AnalysisJob.model_validate_json(body)
        result = await analyse(job, load_image, detect)
        await results.publish(result, message_id=str(job.job_id))
        _log_outcome(result, started)
        return Action.ACK

    jobs.consume(handle_job, prefetch=settings.worker_prefetch)

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
