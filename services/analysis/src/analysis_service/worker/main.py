"""Worker: turns Analysis Jobs into Analysis Results.

Run with ``python -m analysis_service.worker.main``.
"""

import asyncio
import logging
import socket
from contextlib import AsyncExitStack

import httpx
from faststream import FastStream

from analysis_service.queues import (
    JOBS,
    RESULTS,
    Action,
    Queue,
    QueueConfig,
    Received,
    confirming_broker,
)
from analysis_service.settings import WorkerSettings
from analysis_service.uploads import open_store
from analysis_service.worker.analyse import handle_job
from analysis_service.worker.detector import Detect, load_detector
from analysis_service.worker.image_source import ImageSource

# Wikimedia answers 403 to the default python-httpx User-Agent; it wants
# one that names the app and a contact: https://w.wiki/4wJS
USER_AGENT = (
    "people-counter/0.1 (+https://github.com/NoratanS/ZaawansowaneProgramowanie)"
)


class _ImageResources:
    """The Worker's HTTP client and Upload store, opened at startup."""

    def __init__(self, settings: WorkerSettings) -> None:
        self._settings = settings
        self._resources = AsyncExitStack()
        self.source: ImageSource | None = None

    async def open(self) -> None:
        # No per-operation timeout: fetch_image enforces the total limit itself,
        # and httpx's 5 s default would cut it short when the limit is longer.
        http = await self._resources.enter_async_context(
            httpx.AsyncClient(timeout=None, headers={"User-Agent": USER_AGENT})
        )
        # The API creates the bucket, not the Worker.
        store = await self._resources.enter_async_context(open_store(self._settings))
        settings = self._settings
        self.source = ImageSource(
            http,
            store,
            public_url=settings.analysis_public_url,
            max_bytes=settings.image_max_bytes,
            fetch_timeout_seconds=settings.image_fetch_timeout_seconds,
            allowed_hosts=settings.image_allowed_hosts,
        )

    async def aclose(self) -> None:
        await self._resources.aclose()


def build_worker(
    settings: WorkerSettings,
    detect: Detect,
    *,
    jobs: QueueConfig = JOBS,
    results: QueueConfig = RESULTS,
) -> FastStream:
    broker = confirming_broker(settings.rabbitmq_url)
    jobs_queue = Queue(broker, jobs)
    results_queue = Queue(broker, results)
    images = _ImageResources(settings)
    # In compose the hostname is the container id, one per replica.
    worker = socket.gethostname()
    app = FastStream(broker)

    @app.on_startup
    async def start() -> None:
        await images.open()
        # Declare before the subscriber starts consuming from analysis-jobs.
        await broker.connect()
        await jobs_queue.declare()
        await results_queue.declare()

    @app.after_shutdown
    async def close() -> None:
        await images.aclose()

    async def on_job(received: Received) -> Action:
        return await handle_job(
            received.body, images.source.load, detect, results_queue, worker=worker
        )

    jobs_queue.consume(on_job, prefetch=settings.worker_prefetch)

    return app


def main() -> None:
    settings = WorkerSettings()
    logging.basicConfig(level=settings.log_level)
    detect = load_detector(settings.model_path)
    asyncio.run(build_worker(settings, detect).run())


if __name__ == "__main__":
    main()
