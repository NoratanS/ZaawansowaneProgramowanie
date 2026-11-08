import pytest
from pydantic import ValidationError

from results_service.settings import DatabaseSettings, ResultsSettings

DATABASE_URL = "postgresql+asyncpg://u:p@db:5432/results"


@pytest.fixture(autouse=True)
def env(monkeypatch, jwt_keys):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("JWT_PUBLIC_KEY", jwt_keys.public)


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


@pytest.mark.unit
def test_public_key_is_required(monkeypatch):
    monkeypatch.delenv("JWT_PUBLIC_KEY")

    with pytest.raises(ValidationError, match="jwt_public_key"):
        ResultsSettings()


@pytest.mark.unit
def test_public_key_must_be_a_pem_key(monkeypatch):
    monkeypatch.setenv("JWT_PUBLIC_KEY", "not a key")

    with pytest.raises(ValidationError, match="jwt_public_key"):
        ResultsSettings()


@pytest.mark.unit
def test_migrations_need_only_the_database_url(monkeypatch):
    monkeypatch.delenv("JWT_PUBLIC_KEY")

    assert DatabaseSettings().database_url.endswith("/results")


@pytest.mark.unit
def test_public_key_must_be_an_rsa_key(monkeypatch, ec_keys):
    monkeypatch.setenv("JWT_PUBLIC_KEY", ec_keys.public)

    with pytest.raises(ValidationError, match="RSA"):
        ResultsSettings()
