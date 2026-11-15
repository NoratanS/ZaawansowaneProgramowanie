from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from analysis_service.settings import (
    AnalysisApiSettings,
    BaseUrl,
    CourierSettings,
    IssueTokenSettings,
    PublicKeyPem,
    WorkerSettings,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("settings_class", "field", "expected"),
    [
        (AnalysisApiSettings, "s3_endpoint_url", "http://s3:9000/"),
        (AnalysisApiSettings, "analysis_public_url", "http://localhost:8000"),
        (AnalysisApiSettings, "results_public_url", "http://localhost:8001"),
        (WorkerSettings, "s3_endpoint_url", "http://s3:9000/"),
        (WorkerSettings, "analysis_public_url", "http://localhost:8000"),
        (CourierSettings, "results_service_url", "http://results:8000"),
    ],
)
def test_in_network_urls_default_to_the_compose_hosts(
    settings_env, settings_class, field, expected
):
    settings_env(settings_class)

    assert str(getattr(settings_class(), field)) == expected


@pytest.mark.parametrize(
    "settings_class", [AnalysisApiSettings, WorkerSettings, CourierSettings]
)
def test_log_level_defaults_to_info(settings_env, settings_class):
    settings_env(settings_class)

    assert settings_class().log_level == "INFO"


# AnalysisApiSettings


@pytest.fixture
def api_env(settings_env):
    return settings_env(AnalysisApiSettings)


@pytest.mark.parametrize(
    "missing", ["RABBITMQ_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY", "JWT_PUBLIC_KEY"]
)
def test_api_required_settings_must_be_set(api_env, missing):
    api_env.delenv(missing)

    with pytest.raises(ValidationError, match=missing.lower()):
        AnalysisApiSettings()


def test_api_settings_come_from_the_environment(api_env):
    api_env.setenv("S3_ENDPOINT_URL", "http://store:9000")
    api_env.setenv("ANALYSIS_PUBLIC_URL", "https://pc.example/analysis/")
    api_env.setenv("RESULTS_PUBLIC_URL", "https://pc.example/results/")

    settings = AnalysisApiSettings()

    assert settings.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert str(settings.s3_endpoint_url) == "http://store:9000/"
    assert settings.s3_access_key == "access"
    assert settings.s3_secret_key.get_secret_value() == "secret"
    assert settings.analysis_public_url == "https://pc.example/analysis"
    assert settings.results_public_url == "https://pc.example/results"
    # The upload size limit is shared with the Worker.
    assert settings.image_max_bytes == 10 * 1024 * 1024


def test_jwt_public_key_must_be_a_pem_key(api_env):
    api_env.setenv("JWT_PUBLIC_KEY", "not a key")

    with pytest.raises(ValidationError, match="jwt_public_key"):
        AnalysisApiSettings()


def test_jwt_public_key_must_be_an_rsa_key(api_env, ec_keys):
    api_env.setenv("JWT_PUBLIC_KEY", ec_keys.public)

    with pytest.raises(ValidationError, match="RSA"):
        AnalysisApiSettings()


def test_log_level_must_be_a_logging_level(api_env):
    api_env.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError, match="log_level"):
        AnalysisApiSettings()


# WorkerSettings


@pytest.fixture
def worker_env(settings_env):
    return settings_env(WorkerSettings)


@pytest.mark.parametrize("missing", ["RABBITMQ_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY"])
def test_worker_required_settings_must_be_set(worker_env, missing):
    worker_env.delenv(missing)

    with pytest.raises(ValidationError, match=missing.lower()):
        WorkerSettings()


def test_worker_defaults_follow_the_spec(worker_env):
    settings = WorkerSettings()

    assert settings.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert settings.image_fetch_timeout_seconds == 10
    assert settings.image_max_bytes == 10 * 1024 * 1024
    assert settings.worker_prefetch == 1
    assert settings.image_allowed_hosts == frozenset()
    assert settings.model_path == Path(
        "/opt/models/object_detection_yolox_2022nov.onnx"
    )


def test_worker_knobs_come_from_the_environment(worker_env):
    worker_env.setenv("IMAGE_FETCH_TIMEOUT_SECONDS", "0.2")
    worker_env.setenv("IMAGE_MAX_BYTES", "1000")
    worker_env.setenv("WORKER_PREFETCH", "4")
    worker_env.setenv("MODEL_PATH", "/models/yolox.onnx")

    settings = WorkerSettings()

    assert settings.image_fetch_timeout_seconds == 0.2
    assert settings.image_max_bytes == 1000
    assert settings.worker_prefetch == 4
    assert settings.model_path == Path("/models/yolox.onnx")


@pytest.mark.parametrize(
    ("value", "hosts"),
    [
        ("images", {"images"}),
        (" images , Wikimedia.ORG ,", {"images", "wikimedia.org"}),
        ("", set()),
    ],
)
def test_allowed_hosts_are_a_comma_separated_list(worker_env, value, hosts):
    worker_env.setenv("IMAGE_ALLOWED_HOSTS", value)

    assert WorkerSettings().image_allowed_hosts == hosts


@pytest.mark.parametrize(
    "knob",
    ["image_fetch_timeout_seconds", "image_max_bytes", "worker_prefetch"],
)
def test_worker_knobs_must_be_positive(worker_env, knob):
    with pytest.raises(ValidationError, match=knob):
        WorkerSettings(**{knob: 0})


# CourierSettings


@pytest.fixture
def courier_env(settings_env):
    return settings_env(CourierSettings)


@pytest.mark.parametrize("missing", ["RABBITMQ_URL", "JWT_PRIVATE_KEY"])
def test_courier_required_settings_must_be_set(courier_env, missing):
    courier_env.delenv(missing)

    with pytest.raises(ValidationError, match=missing.lower()):
        CourierSettings()


def test_courier_defaults_follow_the_spec(courier_env):
    settings = CourierSettings()

    assert settings.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert settings.delivery_timeout_seconds == 10
    assert settings.courier_prefetch == 10


def test_courier_knobs_come_from_the_environment(courier_env):
    courier_env.setenv("RESULTS_SERVICE_URL", "http://results.internal:9000/")
    courier_env.setenv("DELIVERY_TIMEOUT_SECONDS", "0.2")
    courier_env.setenv("COURIER_PREFETCH", "3")

    settings = CourierSettings()

    assert settings.results_service_url == "http://results.internal:9000"
    assert settings.delivery_timeout_seconds == 0.2
    assert settings.courier_prefetch == 3


@pytest.mark.parametrize("knob", ["delivery_timeout_seconds", "courier_prefetch"])
def test_courier_knobs_must_be_positive(courier_env, knob):
    with pytest.raises(ValidationError, match=knob):
        CourierSettings(**{knob: 0})


def test_jwt_private_key_must_be_a_pem_key(courier_env):
    courier_env.setenv("JWT_PRIVATE_KEY", "not a key")

    with pytest.raises(ValidationError, match="jwt_private_key"):
        CourierSettings()


def test_jwt_private_key_must_be_an_rsa_key(courier_env, ec_keys):
    courier_env.setenv("JWT_PRIVATE_KEY", ec_keys.private)

    with pytest.raises(ValidationError, match="RSA"):
        CourierSettings()


# IssueTokenSettings


@pytest.fixture
def issue_token_env(settings_env):
    return settings_env(IssueTokenSettings)


def test_issue_token_private_key_is_required(issue_token_env):
    issue_token_env.delenv("JWT_PRIVATE_KEY")

    with pytest.raises(ValidationError, match="jwt_private_key"):
        IssueTokenSettings()


def test_issue_token_private_key_comes_from_the_environment(issue_token_env, jwt_keys):
    assert IssueTokenSettings().jwt_private_key.get_secret_value() == jwt_keys.private


def test_issue_token_private_key_is_hidden_from_repr(issue_token_env):
    assert "PRIVATE KEY" not in repr(IssueTokenSettings())


def test_issue_token_private_key_must_be_an_rsa_key(issue_token_env, ec_keys):
    issue_token_env.setenv("JWT_PRIVATE_KEY", ec_keys.private)

    with pytest.raises(ValidationError, match="RSA"):
        IssueTokenSettings()


# Shared field types


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
