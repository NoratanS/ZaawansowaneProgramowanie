"""The Courier mints with analysis_service.auth; the Results Service verifies
with its own copy in results_service.auth. These tests catch drift between them.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from analysis_service.auth import CourierToken, mint
from results_service.auth import require_courier_token

pytestmark = pytest.mark.unit


def _check(public_key, token):
    # The check reads the key where create_app puts the settings.
    settings = SimpleNamespace(jwt_public_key=public_key)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings))
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    require_courier_token()(request, credentials)


def test_the_results_service_accepts_a_courier_token(jwt_keys):
    _check(jwt_keys.public, CourierToken(jwt_keys.private).get())


def test_the_results_service_refuses_a_client_token(jwt_keys):
    token = mint(
        jwt_keys.private, sub="alice", aud="analysis-service", ttl=timedelta(days=30)
    )

    with pytest.raises(HTTPException) as refused:
        _check(jwt_keys.public, token)

    assert refused.value.status_code == 401


def _expired_seconds_ago(jwt_keys, seconds):
    issued = datetime.now(UTC) - timedelta(minutes=5, seconds=seconds)
    return mint(
        jwt_keys.private,
        sub="courier",
        aud="results-service",
        ttl=timedelta(minutes=5),
        now=issued,
    )


def test_both_sides_allow_30_seconds_of_clock_skew(jwt_keys):
    _check(jwt_keys.public, _expired_seconds_ago(jwt_keys, 25))


def test_both_sides_refuse_a_token_past_the_leeway(jwt_keys):
    with pytest.raises(HTTPException):
        _check(jwt_keys.public, _expired_seconds_ago(jwt_keys, 35))
