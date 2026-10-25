"""Settings, read from real env vars only (no ``.env``).

Each entrypoint has one settings class, built from the shared pieces below.
"""

from typing import Annotated, Self

from pydantic import Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings

from analysis_service.queues import QueueConfig

JOBS_QUEUE = "analysis-jobs"

Seconds = Annotated[float, Field(gt=0)]
Limit = Annotated[int, Field(ge=1)]


class BrokerSettings(BaseSettings):
    rabbitmq_url: str


class JobsQueueSettings(BaseSettings):
    jobs_queue_retry_min_seconds: Seconds = 2
    jobs_queue_retry_max_seconds: Seconds = 30
    jobs_queue_delivery_limit: Limit = 3

    @model_validator(mode="after")
    def _retry_min_not_above_max(self) -> Self:
        if self.jobs_queue_retry_min_seconds > self.jobs_queue_retry_max_seconds:
            raise ValueError(
                "jobs_queue_retry_min_seconds must not exceed"
                " jobs_queue_retry_max_seconds"
            )
        return self

    @property
    def jobs_queue(self) -> QueueConfig:
        return QueueConfig(
            name=JOBS_QUEUE,
            retry_min_seconds=self.jobs_queue_retry_min_seconds,
            retry_max_seconds=self.jobs_queue_retry_max_seconds,
            delivery_limit=self.jobs_queue_delivery_limit,
        )


class AnalysisApiSettings(BrokerSettings, JobsQueueSettings):
    """Analysis Service HTTP API settings."""

    results_public_url: HttpUrl
