import pytest
from pydantic import ValidationError

from analysis_service.queues import QueueConfig
from analysis_service.settings import WorkerSettings

pytestmark = pytest.mark.unit

# Every optional setting, so the developer's own env can't leak into defaults.
KNOBS = [name.upper() for name in WorkerSettings.model_fields if name != "rabbitmq_url"]


@pytest.fixture
def env(monkeypatch):
    for name in KNOBS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    return monkeypatch


def test_rabbitmq_url_is_required(env):
    env.delenv("RABBITMQ_URL")

    with pytest.raises(ValidationError, match="rabbitmq_url"):
        WorkerSettings()


def test_defaults_follow_the_spec(env):
    settings = WorkerSettings()

    assert settings.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert settings.image_fetch_timeout_seconds == 10
    assert settings.image_max_bytes == 10 * 1024 * 1024
    assert settings.worker_prefetch == 1
    # jobs_queue defaults are covered by test_settings.py (same mixin).
    assert settings.results_queue == QueueConfig(
        name="analysis-results",
        retry_min_seconds=2,
        retry_max_seconds=60,
        delivery_limit=20,
    )


def test_knobs_come_from_the_environment(env):
    env.setenv("IMAGE_FETCH_TIMEOUT_SECONDS", "0.2")
    env.setenv("IMAGE_MAX_BYTES", "1000")
    env.setenv("WORKER_PREFETCH", "4")
    env.setenv("RESULTS_QUEUE_DELIVERY_LIMIT", "5")

    settings = WorkerSettings()

    assert settings.image_fetch_timeout_seconds == 0.2
    assert settings.image_max_bytes == 1000
    assert settings.worker_prefetch == 4
    assert settings.results_queue.delivery_limit == 5


@pytest.mark.parametrize(
    "knob",
    ["image_fetch_timeout_seconds", "image_max_bytes", "worker_prefetch"],
)
def test_worker_knobs_must_be_positive(env, knob):
    with pytest.raises(ValidationError, match=knob):
        WorkerSettings(**{knob: 0})


def test_results_retry_min_must_not_exceed_retry_max(env):
    with pytest.raises(ValidationError, match="must not exceed"):
        WorkerSettings(
            results_queue_retry_min_seconds=90, results_queue_retry_max_seconds=60
        )
