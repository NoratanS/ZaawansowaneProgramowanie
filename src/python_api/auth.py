"""Password hashing, JWT tokens and the FastAPI dependencies that check them."""

import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Set JWT_SECRET_KEY in production; the fallback is only for local development.
SECRET_KEY = os.environ.get(
    "JWT_SECRET_KEY", "dev-only-secret-key-change-me-in-production"
)
ALGORITHM = "HS256"
TOKEN_LIFETIME = timedelta(minutes=30)

ROLE_ADMIN = "ROLE_ADMIN"

# auto_error=False: we raise 401 ourselves, so a missing header and a bad
# token get the same response.
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Return "salt$hash", with the hash made by PBKDF2-SHA256."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    salt, expected = password_hash.split("$")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return hmac.compare_digest(digest.hex(), expected)


def create_access_token(username: str, roles: list[str]) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": username,
        "roles": roles,
        "iat": now,
        "exp": now + TOKEN_LIFETIME,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict:
    """Dependency: require a valid `Authorization: Bearer <token>` header.

    jwt.decode checks the signature and the `exp` claim.
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


TokenPayload = Annotated[dict, Depends(get_token_payload)]


def require_admin(payload: TokenPayload) -> dict:
    """Dependency: like get_token_payload, but also require ROLE_ADMIN."""
    if ROLE_ADMIN not in payload.get("roles", []):
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload
