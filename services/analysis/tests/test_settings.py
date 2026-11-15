import pytest
from pydantic import TypeAdapter, ValidationError

from analysis_service.queues import QueueConfig
from analysis_service.settings import (
    AnalysisApiSettings,
    BaseUrl,
    CourierSettings,
    PublicKeyPem,
    WorkerSettings,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def env(settings_env):
    return settings_env(AnalysisApiSettings)


@pytest.mark.parametrize(
    "missing",
    [
        "RABBITMQ_URL",
        "RESULTS_PUBLIC_URL",
        "S3_ENDPOINT_URL",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "ANALYSIS_PUBLIC_URL",
        "JWT_PUBLIC_KEY",
    ],
)
def test_required_settings_must_be_set(env, missing):
    env.delenv(missing)

    with pytest.raises(ValidationError, match=missing.lower()):
        AnalysisApiSettings()


def test_required_settings_come_from_the_environment(env):
    settings = AnalysisApiSettings()

    assert settings.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert settings.results_public_url == "http://localhost:8001"
    assert str(settings.s3_endpoint_url) == "http://s3:9000/"
    assert settings.s3_access_key == "access"
    assert settings.s3_secret_key.get_secret_value() == "secret"
    # The upload size limit is shared with the Worker.
    assert settings.image_max_bytes == 10 * 1024 * 1024


def test_jobs_queue_defaults_follow_the_spec(env):
    assert AnalysisApiSettings().jobs_queue == QueueConfig(
        name="analysis-jobs",
        retry_min_seconds=2,
        retry_max_seconds=30,
        delivery_limit=3,
    )


def test_jobs_queue_knobs_come_from_the_environment(env):
    env.setenv("JOBS_QUEUE_DELIVERY_LIMIT", "7")

    assert AnalysisApiSettings().jobs_queue.delivery_limit == 7


def test_retry_delays_must_be_positive(env):
    with pytest.raises(ValidationError, match="jobs_queue_retry_min_seconds"):
        AnalysisApiSettings(jobs_queue_retry_min_seconds=0)


def test_retry_min_must_not_exceed_retry_max(env):
    with pytest.raises(ValidationError, match="must not exceed"):
        AnalysisApiSettings(
            jobs_queue_retry_min_seconds=60, jobs_queue_retry_max_seconds=30
        )


def test_jwt_public_key_must_be_a_pem_key(env):
    env.setenv("JWT_PUBLIC_KEY", "not a key")

    with pytest.raises(ValidationError, match="jwt_public_key"):
        AnalysisApiSettings()


def test_jwt_public_key_must_be_an_rsa_key(env, ec_keys):
    env.setenv("JWT_PUBLIC_KEY", ec_keys.public)

    with pytest.raises(ValidationError, match="RSA"):
        AnalysisApiSettings()


@pytest.mark.parametrize(
    "settings_class", [AnalysisApiSettings, WorkerSettings, CourierSettings]
)
def test_log_level_defaults_to_info(settings_env, settings_class):
    settings_env(settings_class)

    assert settings_class().log_level == "INFO"


def test_log_level_must_be_a_logging_level(env):
    env.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError, match="log_level"):
        AnalysisApiSettings()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://pc.example/analysis/", "https://pc.example/analysis"),
        ("https://pc.example/analysis", "https://pc.example/analysis"),
        ("http://localhost:8000", "http://localhost:8000"),
    ],
)
def test_a_base_url_has_no_trailing_slash(value, expected):
    assert TypeAdapter(BaseUrl).validate_python(value) == expected


def test_a_base_url_must_be_http():
    with pytest.raises(ValidationError, match="URL scheme should be 'http' or 'https'"):
        TypeAdapter(BaseUrl).validate_python("ftp://results")


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
