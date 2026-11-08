"""Settings, read from real env vars only (no ``.env``).

Each entrypoint has one settings class, built from the shared pieces below.
"""

from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)
from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode

from analysis_service.queues import JOBS_QUEUE, RESULTS_QUEUE, QueueConfig

# Where the Analysis image bakes YOLOX-S (see services/analysis/Dockerfile).
BAKED_MODEL_PATH = Path("/opt/models/object_detection_yolox_2022nov.onnx")

Seconds = Annotated[float, Field(gt=0)]
Limit = Annotated[int, Field(ge=1)]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LoggingSettings(BaseSettings):
    log_level: LogLevel = "INFO"


class BrokerSettings(BaseSettings):
    rabbitmq_url: str


class ImageLimitSettings(BaseSettings):
    image_max_bytes: Limit = 10 * 1024 * 1024


class UploadSettings(BaseSettings):
    """The S3-compatible store for uploaded photos, and their public URLs."""

    s3_endpoint_url: HttpUrl
    s3_access_key: str
    s3_secret_key: SecretStr
    # The Analysis Service as the browser sees it; uploads are served under it.
    analysis_public_url: HttpUrl

    @property
    def uploads_base_url(self) -> str:
        """Where ``GET /uploads/{id}`` lives, with no trailing slash."""
        return str(self.analysis_public_url).rstrip("/") + "/uploads"


class JobsQueueSettings(BaseSettings):
    jobs_queue_retry_min_seconds: Seconds = 2
    jobs_queue_retry_max_seconds: Seconds = 30
    jobs_queue_delivery_limit: Limit = 3

    @model_validator(mode="after")
    def _jobs_queue_is_valid(self) -> Self:
        # Fail at startup, not on first use; QueueConfig owns the rules.
        self.jobs_queue
        return self

    @property
    def jobs_queue(self) -> QueueConfig:
        return QueueConfig(
            name=JOBS_QUEUE,
            retry_min_seconds=self.jobs_queue_retry_min_seconds,
            retry_max_seconds=self.jobs_queue_retry_max_seconds,
            delivery_limit=self.jobs_queue_delivery_limit,
        )


class ResultsQueueSettings(BaseSettings):
    results_queue_retry_min_seconds: Seconds = 2
    results_queue_retry_max_seconds: Seconds = 60
    results_queue_delivery_limit: Limit = 20

    @model_validator(mode="after")
    def _results_queue_is_valid(self) -> Self:
        self.results_queue
        return self

    @property
    def results_queue(self) -> QueueConfig:
        return QueueConfig(
            name=RESULTS_QUEUE,
            retry_min_seconds=self.results_queue_retry_min_seconds,
            retry_max_seconds=self.results_queue_retry_max_seconds,
            delivery_limit=self.results_queue_delivery_limit,
        )


class PublicKeySettings(BaseSettings):
    jwt_public_key: str

    @field_validator("jwt_public_key")
    @classmethod
    def _is_an_rsa_public_key(cls, value: str) -> str:
        # RS256 needs RSA; any other key would fail every request, not startup.
        if not isinstance(load_pem_public_key(value.encode()), RSAPublicKey):
            raise ValueError("must be an RSA public key")
        return value


class PrivateKeySettings(BaseSettings):
    # SecretStr keeps the key out of reprs and logs.
    jwt_private_key: SecretStr

    @field_validator("jwt_private_key")
    @classmethod
    def _is_an_rsa_private_key(cls, value: SecretStr) -> SecretStr:
        key = load_pem_private_key(value.get_secret_value().encode(), password=None)
        if not isinstance(key, RSAPrivateKey):
            raise ValueError("must be an RSA private key")
        return value


class AnalysisApiSettings(
    BrokerSettings,
    JobsQueueSettings,
    PublicKeySettings,
    UploadSettings,
    ImageLimitSettings,
    LoggingSettings,
):
    """Analysis Service HTTP API settings."""

    results_public_url: HttpUrl

    @property
    def results_base_url(self) -> str:
        """``results_public_url`` without the trailing slash ``HttpUrl`` may add."""
        return str(self.results_public_url).rstrip("/")

    @property
    def results_origin(self) -> str:
        """Scheme, host and port of ``results_public_url``: where the UI runs."""
        parts = urlsplit(str(self.results_public_url))
        return f"{parts.scheme}://{parts.netloc}"


class WorkerSettings(
    BrokerSettings,
    JobsQueueSettings,
    ResultsQueueSettings,
    UploadSettings,
    ImageLimitSettings,
    LoggingSettings,
):
    """Worker settings."""

    image_fetch_timeout_seconds: Seconds = 10
    # Hosts exempt from the internal-address check, e.g. "images" in e2e.
    image_allowed_hosts: Annotated[frozenset[str], NoDecode] = frozenset()
    worker_prefetch: Limit = 1
    model_path: Path = BAKED_MODEL_PATH

    @field_validator("image_allowed_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: object) -> object:
        # Comma-separated in the env; host names compare lowercase, as httpx gives them.
        if isinstance(value, str):
            return {host.strip().lower() for host in value.split(",") if host.strip()}
        return value


class CourierSettings(
    BrokerSettings, ResultsQueueSettings, PrivateKeySettings, LoggingSettings
):
    """Courier settings."""

    results_service_url: HttpUrl
    delivery_timeout_seconds: Seconds = 10
    courier_prefetch: Limit = 10

    @property
    def results_service_base_url(self) -> str:
        """``results_service_url`` without the trailing slash ``HttpUrl`` may add."""
        return str(self.results_service_url).rstrip("/")


class IssueTokenSettings(PrivateKeySettings):
    """``issue-token`` settings."""
