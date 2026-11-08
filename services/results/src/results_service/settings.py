from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import field_validator
from pydantic_settings import BaseSettings

_ASYNC_SCHEME = "postgresql+asyncpg://"


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

    jwt_public_key: str

    @field_validator("jwt_public_key")
    @classmethod
    def check_rsa_public_key(cls, value: str) -> str:
        # RS256 needs RSA; any other key would fail every PUT, not startup.
        if not isinstance(load_pem_public_key(value.encode()), RSAPublicKey):
            raise ValueError("must be an RSA public key")
        return value
