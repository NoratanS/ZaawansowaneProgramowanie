from pydantic import field_validator
from pydantic_settings import BaseSettings

_ASYNC_SCHEME = "postgresql+asyncpg://"


class ResultsSettings(BaseSettings):
    """Results Service settings, read from real env vars only (no ``.env``)."""

    database_url: str

    @field_validator("database_url")
    @classmethod
    def check_async_driver(cls, value: str) -> str:
        if not value.startswith(_ASYNC_SCHEME):
            raise ValueError(f"database_url must start with {_ASYNC_SCHEME}")
        return value
