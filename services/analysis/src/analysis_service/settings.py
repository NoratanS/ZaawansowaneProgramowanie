"""Settings, read from real env vars only (no ``.env``).

Each entrypoint has one flat settings class; the field types below are shared.
URLs default to the ones the compose stack uses.
"""

from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)
from pydantic import (
    AfterValidator,
    Field,
    HttpUrl,
    SecretStr,
    TypeAdapter,
    field_validator,
)
from pydantic_settings import BaseSettings, NoDecode

# Where the Analysis image bakes YOLOX-S (see services/analysis/Dockerfile).
BAKED_MODEL_PATH = Path("/opt/models/object_detection_yolox_2022nov.onnx")

Seconds = Annotated[float, Field(gt=0)]
Limit = Annotated[int, Field(ge=1)]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_HTTP_URL = TypeAdapter(HttpUrl)


def _without_trailing_slash(value: str) -> str:
    return str(_HTTP_URL.validate_python(value)).rstrip("/")


def _is_an_rsa_public_key(value: str) -> str:
    # RS256 needs RSA; any other key would fail every request, not startup.
    if not isinstance(load_pem_public_key(value.encode()), RSAPublicKey):
        raise ValueError("must be an RSA public key")
    return value


def _is_an_rsa_private_key(value: SecretStr) -> SecretStr:
    key = load_pem_private_key(value.get_secret_value().encode(), password=None)
    if not isinstance(key, RSAPrivateKey):
        raise ValueError("must be an RSA private key")
    return value


# An http(s) URL with no trailing slash, so f"{url}/path" has no double slash.
BaseUrl = Annotated[str, AfterValidator(_without_trailing_slash)]
PublicKeyPem = Annotated[str, AfterValidator(_is_an_rsa_public_key)]
# SecretStr keeps the key out of reprs and logs.
PrivateKeyPem = Annotated[SecretStr, AfterValidator(_is_an_rsa_private_key)]

S3_ENDPOINT_URL = HttpUrl("http://s3:9000")
ANALYSIS_PUBLIC_URL = "http://localhost:8000"


class AnalysisApiSettings(BaseSettings):
    """Analysis Service HTTP API settings."""

    rabbitmq_url: str
    jwt_public_key: PublicKeyPem
    s3_endpoint_url: HttpUrl = S3_ENDPOINT_URL
    s3_access_key: str
    s3_secret_key: SecretStr
    # The Analysis Service as the browser sees it; uploads are served under it.
    analysis_public_url: BaseUrl = ANALYSIS_PUBLIC_URL
    results_public_url: BaseUrl = "http://localhost:8001"
    image_max_bytes: Limit = 10 * 1024 * 1024
    log_level: LogLevel = "INFO"

    @property
    def results_origin(self) -> str:
        """Scheme, host and port of ``results_public_url``: where the UI runs."""
        parts = urlsplit(self.results_public_url)
        return f"{parts.scheme}://{parts.netloc}"


class WorkerSettings(BaseSettings):
    """Worker settings."""

    rabbitmq_url: str
    s3_endpoint_url: HttpUrl = S3_ENDPOINT_URL
    s3_access_key: str
    s3_secret_key: SecretStr
    # Upload URLs start with it; the Worker reads those from the store.
    analysis_public_url: BaseUrl = ANALYSIS_PUBLIC_URL
    image_max_bytes: Limit = 10 * 1024 * 1024
    image_fetch_timeout_seconds: Seconds = 10
    # Hosts exempt from the internal-address check, e.g. "images" in e2e.
    image_allowed_hosts: Annotated[frozenset[str], NoDecode] = frozenset()
    worker_prefetch: Limit = 1
    model_path: Path = BAKED_MODEL_PATH
    log_level: LogLevel = "INFO"

    @field_validator("image_allowed_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: object) -> object:
        # Comma-separated in the env; host names compare lowercase, as httpx gives them.
        if isinstance(value, str):
            return {host.strip().lower() for host in value.split(",") if host.strip()}
        return value


class CourierSettings(BaseSettings):
    """Courier settings."""

    rabbitmq_url: str
    jwt_private_key: PrivateKeyPem
    results_service_url: BaseUrl = "http://results:8000"
    delivery_timeout_seconds: Seconds = 10
    courier_prefetch: Limit = 10
    log_level: LogLevel = "INFO"


class IssueTokenSettings(BaseSettings):
    """``issue-token`` settings."""

    jwt_private_key: PrivateKeyPem
