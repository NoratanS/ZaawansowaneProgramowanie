"""Analysis Service HTTP API: accepts Analysis Requests and queues Analysis Jobs.

It also takes photo uploads: each file is stored and becomes an Analysis Job
whose ``image_url`` points back at ``GET /uploads/{id}``.
"""

from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile

from analysis_service.auth import ANALYSIS_AUDIENCE, require_token
from analysis_service.messages import AnalysisJob
from analysis_service.queues import NotQueued, Queue, confirming_broker
from analysis_service.settings import AnalysisApiSettings
from analysis_service.uploads import open_store, url_for

PORT = 8000
MAX_UPLOAD_FILES = 100


class AnalysisRequest(BaseModel):
    image_url: HttpUrl


class AnalysisAccepted(BaseModel):
    job_id: UUID
    result_url: str


class UploadAccepted(AnalysisAccepted):
    filename: str | None


def create_app(settings: AnalysisApiSettings) -> FastAPI:
    results_base_url = settings.results_base_url

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as stack:
            # A missing queue gives 503 instead of a 202 for a lost job.
            broker = confirming_broker(settings.rabbitmq_url)
            await broker.start()
            stack.push_async_callback(broker.stop)
            jobs = Queue(broker, settings.jobs_queue)
            await jobs.declare()
            store = await stack.enter_async_context(open_store(settings))
            await store.create_bucket_if_missing()
            app.state.jobs = jobs
            app.state.store = store
            yield

    app = FastAPI(title="Analysis Service", lifespan=lifespan)
    # Lets the UI page on the Results Service submit. The middleware answers
    # preflights itself, so they need no token.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.results_origin],
        allow_methods=["POST"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    authorized = Depends(require_token(settings.jwt_public_key, ANALYSIS_AUDIENCE))

    async def queue_job(request: Request, image_url: str) -> AnalysisJob:
        job = AnalysisJob(
            job_id=uuid4(),
            image_url=image_url,
            requested_at=datetime.now(UTC),
        )
        try:
            await request.app.state.jobs.publish(job, message_id=str(job.job_id))
        except NotQueued as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The Analysis Job could not be queued",
            ) from exc
        return job

    def result_url_of(job: AnalysisJob) -> str:
        return f"{results_base_url}/results/{job.job_id}"

    @app.post(
        "/analyses",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=AnalysisAccepted,
        dependencies=[authorized],
    )
    async def accept_analysis_request(
        analysis_request: AnalysisRequest, request: Request, response: Response
    ):
        job = await queue_job(request, str(analysis_request.image_url))
        result_url = result_url_of(job)
        response.headers["Location"] = result_url
        return AnalysisAccepted(job_id=job.job_id, result_url=result_url)

    # The form is read in the handler, not declared as a parameter, so a
    # request without a valid token is refused before its body is read.
    @app.post(
        "/uploads",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=list[UploadAccepted],
        dependencies=[authorized],
    )
    async def accept_uploads(request: Request):
        store = request.app.state.store
        # Starlette spools each file to disk past 1 MB.
        async with request.form() as form:
            files = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
            _check_upload_limits(files, settings.image_max_bytes)
            upload_ids = [uuid4() for _ in files]
            for upload_id, file in zip(upload_ids, files):
                await store.put(
                    upload_id,
                    file.file,
                    file.content_type or "application/octet-stream",
                )
        accepted = []
        for upload_id, file in zip(upload_ids, files):
            job = await queue_job(
                request, url_for(upload_id, settings.uploads_base_url)
            )
            accepted.append(
                UploadAccepted(
                    filename=file.filename,
                    job_id=job.job_id,
                    result_url=result_url_of(job),
                )
            )
        return accepted

    # No token: an <img> can't send one. The random id is the protection.
    @app.get("/uploads/{upload_id}")
    async def serve_upload(upload_id: UUID, request: Request):
        stack = AsyncExitStack()
        upload = await stack.enter_async_context(
            request.app.state.store.open(upload_id)
        )
        if upload is None:
            await stack.aclose()
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such upload")

        async def body():
            async for chunk in upload.chunks:
                yield chunk

        # Only images keep their type, so an uploaded page can't run as one.
        media_type = upload.content_type
        if not media_type.startswith("image/"):
            media_type = "application/octet-stream"
        return StreamingResponse(
            body(),
            media_type=media_type,
            headers={
                "Content-Length": str(upload.length),
                "X-Content-Type-Options": "nosniff",
                # An SVG opened directly could otherwise run script here.
                "Content-Security-Policy": "sandbox",
            },
            # Closes the S3 stream, also when the client goes away mid-way.
            background=BackgroundTask(stack.aclose),
        )

    return app


def _check_upload_limits(files: list[UploadFile], max_bytes: int) -> None:
    if not files:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Send one or more files"
        )
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Send at most {MAX_UPLOAD_FILES} files",
        )
    for file in files:
        if file.size is not None and file.size > max_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"{file.filename} is over the {max_bytes}-byte limit",
            )


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
