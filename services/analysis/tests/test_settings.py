import pytest
from pydantic import ValidationError

from analysis_service.queues import QueueConfig
from analysis_service.settings import (
    AnalysisApiSettings,
    CourierSettings,
    WorkerSettings,
)

pytestmark = pytest.mark.unit

REQUIRED = {
    "RABBITMQ_URL": "amqp://guest:guest@rabbitmq:5672/",
    "RESULTS_PUBLIC_URL": "http://localhost:8001",
    "S3_ENDPOINT_URL": "http://s3:9000",
    "S3_ACCESS_KEY": "access",
    "S3_SECRET_KEY": "secret",
    "ANALYSIS_PUBLIC_URL": "http://localhost:8000",
}
KNOBS = [
    "JOBS_QUEUE_RETRY_MIN_SECONDS",
    "JOBS_QUEUE_RETRY_MAX_SECONDS",
    "JOBS_QUEUE_DELIVERY_LIMIT",
    "IMAGE_MAX_BYTES",
]


@pytest.fixture
def env(monkeypatch, jwt_keys):
    monkeypatch.setenv("JWT_PUBLIC_KEY", jwt_keys.public)
    for name in KNOBS:
        monkeypatch.delenv(name, raising=False)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


@pytest.mark.parametrize("missing", [*REQUIRED, "JWT_PUBLIC_KEY"])
def test_required_settings_must_be_set(env, missing):
    env.delenv(missing)

    with pytest.raises(ValidationError, match=missing.lower()):
        AnalysisApiSettings()


def test_required_settings_come_from_the_environment(env):
    settings = AnalysisApiSettings()

    assert settings.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert settings.results_base_url == "http://localhost:8001"
    assert str(settings.s3_endpoint_url) == "http://s3:9000/"
    assert settings.s3_access_key == "access"
    assert settings.s3_secret_key.get_secret_value() == "secret"
    # The upload size limit is shared with the Worker.
    assert settings.image_max_bytes == 10 * 1024 * 1024


@pytest.mark.parametrize(
    "analysis_public_url",
    ["https://pc.example/analysis", "https://pc.example/analysis/"],
)
def test_uploads_are_served_under_the_analysis_public_url(env, analysis_public_url):
    env.setenv("ANALYSIS_PUBLIC_URL", analysis_public_url)

    expected = "https://pc.example/analysis/uploads"
    assert AnalysisApiSettings().uploads_base_url == expected


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


def test_results_public_url_must_be_http(env):
    env.setenv("RESULTS_PUBLIC_URL", "ftp://results")

    with pytest.raises(ValidationError, match="results_public_url"):
        AnalysisApiSettings()


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
def test_log_level_defaults_to_info(env, jwt_keys, settings_class):
    env.delenv("LOG_LEVEL", raising=False)
    env.setenv("JWT_PRIVATE_KEY", jwt_keys.private)
    env.setenv("RESULTS_SERVICE_URL", "http://results:8000")

    assert settings_class().log_level == "INFO"


def test_log_level_must_be_a_logging_level(env):
    env.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError, match="log_level"):
        AnalysisApiSettings()
