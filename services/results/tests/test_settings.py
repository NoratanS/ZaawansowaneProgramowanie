import pytest
from pydantic import ValidationError

from results_service.settings import ResultsSettings


@pytest.mark.unit
def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        ResultsSettings()


@pytest.mark.unit
def test_database_url_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/results")

    assert ResultsSettings().database_url == "postgresql+asyncpg://u:p@db:5432/results"


@pytest.mark.unit
def test_database_url_must_use_the_asyncpg_driver(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/results")

    with pytest.raises(ValidationError, match="postgresql\\+asyncpg://"):
        ResultsSettings()
