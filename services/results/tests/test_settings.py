import pytest
from pydantic import TypeAdapter, ValidationError

from results_service.settings import (
    BaseUrl,
    DatabaseSettings,
    PublicKeyPem,
    ResultsSettings,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def env(settings_env):
    return settings_env(ResultsSettings)


def test_database_url_is_required(env):
    env.delenv("DATABASE_URL")

    with pytest.raises(ValidationError):
        ResultsSettings()


def test_database_url_comes_from_the_environment(env):
    assert ResultsSettings().database_url == "postgresql+asyncpg://u:p@db:5432/results"


def test_database_url_must_use_the_asyncpg_driver(env):
    env.setenv("DATABASE_URL", "postgresql://u:p@db:5432/results")

    with pytest.raises(ValidationError, match="postgresql\\+asyncpg://"):
        ResultsSettings()


def test_public_key_is_required(env):
    env.delenv("JWT_PUBLIC_KEY")

    with pytest.raises(ValidationError, match="jwt_public_key"):
        ResultsSettings()


def test_public_key_must_be_a_pem_key(env):
    env.setenv("JWT_PUBLIC_KEY", "not a key")

    with pytest.raises(ValidationError, match="jwt_public_key"):
        ResultsSettings()


def test_migrations_need_only_the_database_url(settings_env):
    settings_env(DatabaseSettings)

    assert DatabaseSettings().database_url.endswith("/results")


def test_public_key_must_be_an_rsa_key(env, ec_keys):
    env.setenv("JWT_PUBLIC_KEY", ec_keys.public)

    with pytest.raises(ValidationError, match="RSA"):
        ResultsSettings()


def test_log_level_defaults_to_info(env):
    assert ResultsSettings().log_level == "INFO"


def test_log_level_must_be_a_logging_level(env):
    env.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError, match="log_level"):
        ResultsSettings()


def test_analysis_public_url_defaults_to_localhost(env):
    assert ResultsSettings().analysis_public_url == "http://localhost:8000"


def test_analysis_public_url_comes_from_the_environment(env):
    env.setenv("ANALYSIS_PUBLIC_URL", "https://analysis.example")

    assert ResultsSettings().analysis_public_url == "https://analysis.example"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://analysis.example/", "https://analysis.example"),
        ("https://pc.example/analysis", "https://pc.example/analysis"),
        ("http://localhost:8000", "http://localhost:8000"),
    ],
)
def test_a_base_url_has_no_trailing_slash(value, expected):
    assert TypeAdapter(BaseUrl).validate_python(value) == expected


def test_a_base_url_must_be_http():
    with pytest.raises(ValidationError, match="URL scheme should be 'http' or 'https'"):
        TypeAdapter(BaseUrl).validate_python("ftp://analysis")


def test_a_public_key_pem_is_an_rsa_public_key(jwt_keys):
    assert TypeAdapter(PublicKeyPem).validate_python(jwt_keys.public) == jwt_keys.public


@pytest.mark.parametrize("key", ["private", "garbage", "ec"])
def test_a_public_key_pem_rejects_anything_else(jwt_keys, ec_keys, key):
    value = {
        "private": jwt_keys.private,
        "garbage": "not a key",
        "ec": ec_keys.public,
    }[key]

    with pytest.raises(ValidationError):
        TypeAdapter(PublicKeyPem).validate_python(value)
