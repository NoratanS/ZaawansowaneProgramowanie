"""JWT auth on the write edges: RS256 tokens with one key pair.

The Courier and ``issue-token`` hold the private key and mint tokens. The
Analysis Service (and the Results Service, in its own copy) verify with the public
key and accept only their own ``aud``. Client tokens are what API clients
send to the Analysis Service.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ISSUER = "people-counter"
ALGORITHM = "RS256"
LEEWAY_SECONDS = 30
ANALYSIS_AUDIENCE = "analysis-service"
RESULTS_AUDIENCE = "results-service"
COURIER_TOKEN_TTL = timedelta(minutes=5)
COURIER_TOKEN_REFRESH_MARGIN = timedelta(minutes=1)

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def mint(
    private_key: str | RSAPrivateKey,
    *,
    sub: str,
    aud: str,
    ttl: timedelta,
    now: datetime | None = None,
) -> str:
    """Sign a token for ``aud`` that expires ``ttl`` after ``now``."""
    issued_at = int((now or _utcnow()).timestamp())
    claims = {
        "iss": ISSUER,
        "sub": sub,
        "aud": aud,
        "iat": issued_at,
        "exp": issued_at + int(ttl.total_seconds()),
    }
    return jwt.encode(claims, private_key, algorithm=ALGORITHM)


def verify(public_key: str, token: str, *, audience: str) -> dict:
    """Return the token's claims; raise ``jwt.InvalidTokenError`` if it is bad."""
    return jwt.decode(
        token,
        public_key,
        algorithms=[ALGORITHM],
        audience=audience,
        issuer=ISSUER,
        leeway=LEEWAY_SECONDS,
        options={"require": ["iss", "sub", "aud", "iat", "exp"]},
    )


def require_token(public_key: str, audience: str):
    """A FastAPI dependency that lets only valid tokens for ``audience`` through.

    Any failure is ``401`` with ``WWW-Authenticate: Bearer``.
    """
    # Its default auto_error already answers a missing or non-Bearer header
    # with 401 + WWW-Authenticate: Bearer.
    bearer = HTTPBearer()

    def check(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> None:
        try:
            verify(public_key, credentials.credentials, audience=audience)
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    return check


class CourierToken:
    """The Courier's own ``results-service`` token, re-minted before it expires."""

    def __init__(self, private_key: str, clock: Clock = _utcnow):
        # Parse the PEM once: PyJWT would re-parse a string key on every mint.
        self._private_key = load_pem_private_key(private_key.encode(), password=None)
        self._clock = clock
        self._token = ""
        self._expires_at = datetime.min.replace(tzinfo=UTC)

    def get(self) -> str:
        now = self._clock()
        if self._expires_at - now < COURIER_TOKEN_REFRESH_MARGIN:
            self._token = mint(
                self._private_key,
                sub="courier",
                aud=RESULTS_AUDIENCE,
                ttl=COURIER_TOKEN_TTL,
                now=now,
            )
            self._expires_at = now + COURIER_TOKEN_TTL
        return self._token
