from pathlib import Path

import pytest
from pydantic import ValidationError

from analysis_service.queues import QueueConfig
from analysis_service.settings import WorkerSettings

pytestmark = pytest.mark.unit


@pytest.fixture
def env(settings_env):
    return settings_env(WorkerSettings)


@pytest.mark.parametrize(
    "missing",
    [
        "RABBITMQ_URL",
        "S3_ENDPOINT_URL",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "ANALYSIS_PUBLIC_URL",
    ],
)
def test_required_settings_must_be_set(env, missing):
    env.delenv(missing)

    with pytest.raises(ValidationError, match=missing.lower()):
        WorkerSettings()


def test_defaults_follow_the_spec(env):
    settings = WorkerSettings()

    assert settings.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert settings.image_fetch_timeout_seconds == 10
    assert settings.image_max_bytes == 10 * 1024 * 1024
    assert settings.worker_prefetch == 1
    assert settings.image_allowed_hosts == frozenset()
    assert settings.analysis_public_url == "http://localhost:8000"
    assert settings.model_path == Path(
        "/opt/models/object_detection_yolox_2022nov.onnx"
    )
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
    env.setenv("MODEL_PATH", "/models/yolox.onnx")

    settings = WorkerSettings()

    assert settings.image_fetch_timeout_seconds == 0.2
    assert settings.image_max_bytes == 1000
    assert settings.worker_prefetch == 4
    assert settings.results_queue.delivery_limit == 5
    assert settings.model_path == Path("/models/yolox.onnx")


@pytest.mark.parametrize(
    ("value", "hosts"),
    [
        ("images", {"images"}),
        (" images , Wikimedia.ORG ,", {"images", "wikimedia.org"}),
        ("", set()),
    ],
)
def test_allowed_hosts_are_a_comma_separated_list(env, value, hosts):
    env.setenv("IMAGE_ALLOWED_HOSTS", value)

    assert WorkerSettings().image_allowed_hosts == hosts


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
