from datetime import UTC, datetime, timedelta

import jwt
import pytest

from analysis_service.auth import CourierToken, mint, verify

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def test_minted_token_carries_the_spec_claims(jwt_keys, read_token):
    token = mint(
        jwt_keys.private,
        sub="alice",
        aud="analysis-service",
        ttl=timedelta(seconds=60),
        now=NOW,
    )

    header = jwt.get_unverified_header(token)
    claims = read_token(token, "analysis-service")
    assert header["alg"] == "RS256"
    assert claims == {
        "iss": "people-counter",
        "sub": "alice",
        "aud": "analysis-service",
        "iat": 1792929600,
        "exp": 1792929660,
    }


def test_verify_accepts_a_token_for_its_audience(jwt_keys, mint_token):
    token = mint_token("results-service", sub="courier")

    claims = verify(jwt_keys.public, token, audience="results-service")

    assert claims["sub"] == "courier"


def _expired(seconds_ago):
    now = int(datetime.now(UTC).timestamp())
    return {"iat": now - 600, "exp": now - seconds_ago}


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "analysis-service"},
        {"iss": "someone-else"},
        _expired(seconds_ago=31),
    ],
    ids=["wrong-aud", "wrong-iss", "expired-past-leeway"],
)
def test_verify_rejects_bad_claims(jwt_keys, mint_token, claims):
    token = mint_token(**{"aud": "results-service"} | claims)

    with pytest.raises(jwt.InvalidTokenError):
        verify(jwt_keys.public, token, audience="results-service")


def test_verify_allows_30_seconds_of_clock_skew(jwt_keys, mint_token):
    token = mint_token("results-service", **_expired(seconds_ago=20))

    verify(jwt_keys.public, token, audience="results-service")


def test_verify_rejects_a_token_signed_with_another_key(
    jwt_keys, other_jwt_keys, mint_token
):
    token = mint_token("results-service", private_key=other_jwt_keys.private)

    with pytest.raises(jwt.InvalidTokenError):
        verify(jwt_keys.public, token, audience="results-service")


def test_verify_rejects_an_hs256_token_keyed_with_the_public_key(jwt_keys):
    # The classic algorithm-confusion forgery: only RS256 may be accepted.
    token = jwt.encode(
        {"iss": "people-counter", "aud": "results-service", "exp": 2**40},
        "not-the-private-key",
        algorithm="HS256",
    )

    with pytest.raises(jwt.InvalidTokenError):
        verify(jwt_keys.public, token, audience="results-service")


@pytest.mark.parametrize("missing", ["iss", "sub", "aud", "iat", "exp"])
def test_verify_requires_every_claim(jwt_keys, missing):
    now = int(datetime.now(UTC).timestamp())
    claims = {
        "iss": "people-counter",
        "sub": "x",
        "aud": "results-service",
        "iat": now,
        "exp": now + 60,
    }
    del claims[missing]
    token = jwt.encode(claims, jwt_keys.private, algorithm="RS256")

    with pytest.raises(jwt.InvalidTokenError):
        verify(jwt_keys.public, token, audience="results-service")


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


def test_courier_token_is_a_5_minute_results_service_token(jwt_keys):
    token = CourierToken(jwt_keys.private).get()

    claims = verify(jwt_keys.public, token, audience="results-service")
    assert claims["sub"] == "courier"
    assert claims["exp"] - claims["iat"] == 300


def test_courier_token_is_reused_while_a_minute_or_more_is_left(jwt_keys):
    clock = Clock()
    courier_token = CourierToken(jwt_keys.private, clock=clock)
    first = courier_token.get()

    clock.now = NOW + timedelta(minutes=4)

    assert courier_token.get() == first


def test_courier_token_is_reminted_when_less_than_a_minute_is_left(
    jwt_keys, read_token
):
    clock = Clock()
    courier_token = CourierToken(jwt_keys.private, clock=clock)
    first = courier_token.get()

    clock.now = NOW + timedelta(minutes=4, seconds=1)
    second = courier_token.get()

    assert second != first
    first_exp = read_token(first, "results-service")["exp"]
    assert read_token(second, "results-service")["exp"] == first_exp + 241
