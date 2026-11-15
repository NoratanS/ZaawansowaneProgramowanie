"""Worker: turns Analysis Jobs into Analysis Results.

Run with ``python -m analysis_service.worker.main``.
"""

import asyncio
import logging
import socket
from contextlib import AsyncExitStack

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
from analysis_service.worker.analyse import handle_job
from analysis_service.worker.detector import Detect, load_detector
from analysis_service.worker.images import LoadImage, open_image_source


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
    resources = AsyncExitStack()
    load: LoadImage | None = None
    # In compose the hostname is the container id, one per replica.
    worker = socket.gethostname()
    app = FastStream(broker)

    @app.on_startup
    async def start() -> None:
        nonlocal load
        load = await resources.enter_async_context(open_image_source(settings))
        # Declare before the subscriber starts consuming from analysis-jobs.
        await broker.connect()
        await jobs_queue.declare()
        await results_queue.declare()

    @app.after_shutdown
    async def close() -> None:
        await resources.aclose()

    async def on_job(received: Received) -> Action:
        return await handle_job(
            received.body, load, detect, results_queue, worker=worker
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
