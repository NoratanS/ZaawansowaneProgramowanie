from pydantic_settings import BaseSettings


class ResultsSettings(BaseSettings):
    """Results Service settings, read from real env vars only (no ``.env``)."""

    database_url: str
