import pytest
from pydantic import ValidationError

from analysis_service.settings import IssueTokenSettings

pytestmark = pytest.mark.unit


@pytest.fixture
def env(settings_env):
    return settings_env(IssueTokenSettings)


def test_private_key_is_required(env):
    env.delenv("JWT_PRIVATE_KEY")

    with pytest.raises(ValidationError, match="jwt_private_key"):
        IssueTokenSettings()


def test_private_key_comes_from_the_environment(env, jwt_keys):
    assert IssueTokenSettings().jwt_private_key.get_secret_value() == jwt_keys.private


def test_private_key_is_hidden_from_repr(env):
    assert "PRIVATE KEY" not in repr(IssueTokenSettings())
