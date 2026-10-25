"""Analysis Service HTTP API: accepts Analysis Requests and queues Analysis Jobs."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from aiormq.exceptions import AMQPError, ChannelInvalidStateError
from fastapi import FastAPI, HTTPException, Request, Response, status
from faststream.rabbit import RabbitBroker
from faststream.rabbit.schemas import Channel
from pydantic import BaseModel, HttpUrl

from analysis_service.messages import AnalysisJob
from analysis_service.queues import declare_queue
from analysis_service.settings import AnalysisApiSettings

# How long a request waits for the broker to confirm the publish.
PUBLISH_TIMEOUT_SECONDS = 5.0


class AnalysisRequest(BaseModel):
    image_url: HttpUrl


class AnalysisAccepted(BaseModel):
    job_id: UUID
    result_url: str


def create_app(settings: AnalysisApiSettings) -> FastAPI:
    results_base_url = settings.results_base_url
    jobs_queue = settings.jobs_queue

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # on_return_raises turns an unroutable publish into an error, so a
        # missing queue gives 503 instead of a 202 for a lost job.
        broker = RabbitBroker(
            settings.rabbitmq_url, default_channel=Channel(on_return_raises=True)
        )
        await broker.start()
        try:
            await declare_queue(broker, jobs_queue)
            app.state.broker = broker
            yield
        finally:
            await broker.stop()

    app = FastAPI(title="Analysis Service", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post(
        "/analyses",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=AnalysisAccepted,
    )
    async def accept_analysis_request(
        analysis_request: AnalysisRequest, request: Request, response: Response
    ):
        job = AnalysisJob(
            job_id=uuid4(),
            image_url=analysis_request.image_url,
            requested_at=datetime.now(UTC),
        )
        try:
            await request.app.state.broker.publish(
                job,
                queue=jobs_queue.name,
                persist=True,
                message_id=str(job.job_id),
                timeout=PUBLISH_TIMEOUT_SECONDS,
            )
        except (
            AMQPError,  # returned (unroutable) or nacked by the broker
            ChannelInvalidStateError,  # connection lost, reconnect pending
            TimeoutError,  # no confirm within PUBLISH_TIMEOUT_SECONDS
        ) as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The Analysis Job could not be queued",
            ) from exc
        result_url = f"{results_base_url}/results/{job.job_id}"
        response.headers["Location"] = result_url
        return AnalysisAccepted(job_id=job.job_id, result_url=result_url)

    return app
