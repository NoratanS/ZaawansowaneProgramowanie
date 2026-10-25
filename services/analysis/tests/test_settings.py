import pytest
from pydantic import ValidationError

from analysis_service.queues import QueueConfig
from analysis_service.settings import AnalysisApiSettings

pytestmark = pytest.mark.unit

REQUIRED = {
    "RABBITMQ_URL": "amqp://guest:guest@rabbitmq:5672/",
    "RESULTS_PUBLIC_URL": "http://localhost:8001",
}
KNOBS = [
    "JOBS_QUEUE_RETRY_MIN_SECONDS",
    "JOBS_QUEUE_RETRY_MAX_SECONDS",
    "JOBS_QUEUE_DELIVERY_LIMIT",
]


@pytest.fixture
def env(monkeypatch):
    for name in [*REQUIRED, *KNOBS]:
        monkeypatch.delenv(name, raising=False)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


@pytest.mark.parametrize("missing", REQUIRED)
def test_required_settings_must_be_set(env, missing):
    env.delenv(missing)

    with pytest.raises(ValidationError, match=missing.lower()):
        AnalysisApiSettings()


def test_required_settings_come_from_the_environment(env):
    settings = AnalysisApiSettings()

    assert settings.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert str(settings.results_public_url).startswith("http://localhost:8001")


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
