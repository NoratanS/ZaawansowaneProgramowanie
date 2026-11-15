"""Analysis Service HTTP API: accepts Analysis Requests and queues Analysis Jobs.

It also takes photo uploads: each file is stored and becomes an Analysis Job
whose ``image_url`` points back at ``GET /uploads/{id}``.

Run with ``python -m analysis_service.api.main``.
"""

from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import BinaryIO, Protocol
from uuid import UUID

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analysis_service.api.routes import router
from analysis_service.queues import (
    JOBS,
    Publisher,
    Queue,
    QueueConfig,
    confirming_broker,
)
from analysis_service.settings import AnalysisApiSettings
from analysis_service.uploads import StoredUpload, UploadStore, open_store

PORT = 8000


class UploadStorage(Protocol):
    """What the API needs from the Upload store (``UploadStore`` in production)."""

    async def create_bucket_if_missing(self) -> None: ...

    async def put(self, upload_id: UUID, file: BinaryIO, content_type: str) -> None: ...

    def open(
        self, upload_id: UUID
    ) -> AbstractAsyncContextManager[StoredUpload | None]: ...


def create_app(
    settings: AnalysisApiSettings,
    jobs: Publisher | None = None,
    store: UploadStorage | None = None,
    *,
    jobs_queue: QueueConfig = JOBS,
) -> FastAPI:
    """The API; a ``None`` adapter is replaced by the real RabbitMQ or S3 one."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as stack:
            app.state.jobs = (
                await _open_jobs(settings, jobs_queue, stack) if jobs is None else jobs
            )
            app.state.store = (
                await _open_store(settings, stack) if store is None else store
            )
            yield

    app = FastAPI(title="Analysis Service", lifespan=lifespan)
    app.state.settings = settings
    # Lets the UI page on the Results Service submit. The middleware answers
    # preflights itself, so they need no token.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.results_origin],
        allow_methods=["POST"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )
    app.include_router(router)
    return app


async def _open_jobs(
    settings: AnalysisApiSettings, config: QueueConfig, stack: AsyncExitStack
) -> Queue:
    # A missing queue gives 503 instead of a 202 for a lost job.
    broker = confirming_broker(settings.rabbitmq_url)
    await broker.start()
    stack.push_async_callback(broker.stop)
    jobs = Queue(broker, config)
    await jobs.declare()
    return jobs


async def _open_store(
    settings: AnalysisApiSettings, stack: AsyncExitStack
) -> UploadStore:
    store = await stack.enter_async_context(open_store(settings))
    await store.create_bucket_if_missing()
    return store


def main() -> None:
    settings = AnalysisApiSettings()
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",
        port=PORT,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
