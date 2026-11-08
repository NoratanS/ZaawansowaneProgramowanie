"""Shared integration fixtures: real Postgres and RabbitMQ, started on demand.

The containers start the first time a test asks for them and stop at the end of
the session, so unit runs never touch Docker.
The JWT fixtures mint tokens with plain PyJWT, independently of the services.
"""

import functools
import time
from typing import NamedTuple

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.rabbitmq import RabbitMqContainer


@pytest.fixture(scope="session")
def postgres_url():
    """SQLAlchemy URL (``postgresql+asyncpg://...``) of a throwaway Postgres."""
    with PostgresContainer("postgres:18", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def rabbitmq():
    """A throwaway RabbitMQ container, for tests that need to poke the broker."""
    with RabbitMqContainer("rabbitmq:4.3-management") as rabbitmq:
        yield rabbitmq


@pytest.fixture(scope="session")
def rabbitmq_url(rabbitmq):
    """AMQP URL of the throwaway RabbitMQ."""
    params = rabbitmq.get_connection_params()
    return (
        f"amqp://{rabbitmq.username}:{rabbitmq.password}"
        f"@{params.host}:{params.port}/"
    )


class KeyPair(NamedTuple):
    private: str
    public: str


def _pem_pair(key=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return KeyPair(private, public)


@pytest.fixture(scope="session")
def jwt_keys():
    """A throwaway RS256 key pair of PEM strings."""
    return _pem_pair()


@pytest.fixture(scope="session")
def other_jwt_keys():
    """A second key pair, for tokens signed with the wrong key."""
    return _pem_pair()


@pytest.fixture(scope="session")
def ec_keys():
    """A valid PEM pair that is not RSA, which RS256 can't use."""
    return _pem_pair(ec.generate_private_key(ec.SECP256R1()))


@pytest.fixture(scope="session")
def mint_token(jwt_keys):
    """Mint a token the way the spec describes; override any claim."""

    def mint(aud, private_key=None, **claims):
        now = int(time.time())
        payload = {
            "iss": "people-counter",
            "sub": "test",
            "aud": aud,
            "iat": now,
            "exp": now + 300,
        } | claims
        key = _loaded_private_key(private_key or jwt_keys.private)
        return jwt.encode(payload, key, algorithm="RS256")

    return mint


@functools.cache
def _loaded_private_key(pem):
    # PyJWT re-parses a PEM string on every encode (~40 ms); parse it once.
    return serialization.load_pem_private_key(pem.encode(), password=None)


@pytest.fixture(scope="session")
def read_token(jwt_keys):
    """Decode a token signed with ``jwt_keys``, checking ``aud`` and ``iss``.

    Expiry is not checked, so tests can read tokens minted at a fixed past time.
    """

    def read(token, aud):
        return jwt.decode(
            token,
            jwt_keys.public,
            algorithms=["RS256"],
            audience=aud,
            issuer="people-counter",
            options={"verify_exp": False},
        )

    return read


AUDIENCES = ("analysis-service", "results-service")


@pytest.fixture(params=["garbage", "wrong aud", "expired", "another key"])
def bad_token_for(request, mint_token, other_jwt_keys):
    """Build one kind of token that ``aud`` must refuse (one test per kind)."""

    def build(aud):
        long_ago = int(time.time()) - 3600
        match request.param:
            case "garbage":
                return "not-a-jwt"
            case "wrong aud":  # e.g. a client token on PUT /results
                [other_aud] = set(AUDIENCES) - {aud}
                return mint_token(other_aud)
            case "expired":
                return mint_token(aud, iat=long_ago, exp=long_ago + 60)
            case "another key":
                return mint_token(aud, private_key=other_jwt_keys.private)

    return build
