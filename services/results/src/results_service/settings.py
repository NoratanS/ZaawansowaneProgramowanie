from typing import Annotated, Literal

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import AfterValidator, HttpUrl, TypeAdapter, field_validator
from pydantic_settings import BaseSettings

_ASYNC_SCHEME = "postgresql+asyncpg://"
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_HTTP_URL = TypeAdapter(HttpUrl)


def _without_trailing_slash(value: str) -> str:
    return str(_HTTP_URL.validate_python(value)).rstrip("/")


def _is_an_rsa_public_key(value: str) -> str:
    # RS256 needs RSA; any other key would fail every PUT, not startup.
    if not isinstance(load_pem_public_key(value.encode()), RSAPublicKey):
        raise ValueError("must be an RSA public key")
    return value


# An http(s) URL with no trailing slash, so f"{url}/path" has no double slash.
BaseUrl = Annotated[str, AfterValidator(_without_trailing_slash)]
PublicKeyPem = Annotated[str, AfterValidator(_is_an_rsa_public_key)]


class DatabaseSettings(BaseSettings):
    """What Alembic needs, read from real env vars only (no ``.env``)."""

    database_url: str

    @field_validator("database_url")
    @classmethod
    def check_async_driver(cls, value: str) -> str:
        if not value.startswith(_ASYNC_SCHEME):
            raise ValueError(f"database_url must start with {_ASYNC_SCHEME}")
        return value


class ResultsSettings(DatabaseSettings):
    """Results Service settings."""

    jwt_public_key: PublicKeyPem
    log_level: LogLevel = "INFO"
    # Where the UI page sends Analysis Requests, as the browser sees it.
    analysis_public_url: BaseUrl = "http://localhost:8000"
