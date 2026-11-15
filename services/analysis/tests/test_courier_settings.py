import pytest
from pydantic import ValidationError

from analysis_service.queues import QueueConfig
from analysis_service.settings import CourierSettings

pytestmark = pytest.mark.unit


@pytest.fixture
def env(settings_env):
    return settings_env(CourierSettings)


@pytest.mark.parametrize(
    "missing", ["RABBITMQ_URL", "RESULTS_SERVICE_URL", "JWT_PRIVATE_KEY"]
)
def test_required_settings_must_be_set(env, missing):
    env.delenv(missing)

    with pytest.raises(ValidationError, match=missing.lower()):
        CourierSettings()


def test_defaults_follow_the_spec(env):
    settings = CourierSettings()

    assert settings.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert settings.results_service_url == "http://results:8000"
    assert settings.delivery_timeout_seconds == 10
    assert settings.courier_prefetch == 10
    assert settings.results_queue == QueueConfig(
        name="analysis-results",
        retry_min_seconds=2,
        retry_max_seconds=60,
        delivery_limit=20,
    )


def test_knobs_come_from_the_environment(env):
    env.setenv("DELIVERY_TIMEOUT_SECONDS", "0.2")
    env.setenv("COURIER_PREFETCH", "3")
    env.setenv("RESULTS_QUEUE_DELIVERY_LIMIT", "4")

    settings = CourierSettings()

    assert settings.delivery_timeout_seconds == 0.2
    assert settings.courier_prefetch == 3
    assert settings.results_queue.delivery_limit == 4


@pytest.mark.parametrize("knob", ["delivery_timeout_seconds", "courier_prefetch"])
def test_courier_knobs_must_be_positive(env, knob):
    with pytest.raises(ValidationError, match=knob):
        CourierSettings(**{knob: 0})


def test_jwt_private_key_must_be_a_pem_key(env):
    env.setenv("JWT_PRIVATE_KEY", "not a key")

    with pytest.raises(ValidationError, match="jwt_private_key"):
        CourierSettings()


def test_jwt_private_key_must_be_an_rsa_key(env, ec_keys):
    env.setenv("JWT_PRIVATE_KEY", ec_keys.private)

    with pytest.raises(ValidationError, match="RSA"):
        CourierSettings()
