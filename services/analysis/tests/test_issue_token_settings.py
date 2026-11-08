import pytest
from pydantic import ValidationError

from analysis_service.settings import IssueTokenSettings

pytestmark = pytest.mark.unit


def test_private_key_is_required(monkeypatch):
    monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)

    with pytest.raises(ValidationError, match="jwt_private_key"):
        IssueTokenSettings()


def test_private_key_comes_from_the_environment(monkeypatch, jwt_keys):
    monkeypatch.setenv("JWT_PRIVATE_KEY", jwt_keys.private)

    assert IssueTokenSettings().jwt_private_key.get_secret_value() == jwt_keys.private


def test_private_key_is_hidden_from_repr(monkeypatch, jwt_keys):
    monkeypatch.setenv("JWT_PRIVATE_KEY", jwt_keys.private)

    assert "PRIVATE KEY" not in repr(IssueTokenSettings())
