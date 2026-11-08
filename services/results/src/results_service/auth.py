"""Bearer JWT check for ``PUT /results/{job_id}``.

Only the Courier's tokens (``aud: "results-service"``) get through. This
service holds only the public key, so it can verify tokens but never mint them.
Keep in step with ``analysis_service.auth``, which mints them.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ISSUER = "people-counter"
ALGORITHM = "RS256"
AUDIENCE = "results-service"
LEEWAY_SECONDS = 30


def require_courier_token(public_key: str):
    """A FastAPI dependency; any failure is ``401`` + ``WWW-Authenticate: Bearer``."""
    # Its default auto_error already answers a missing or non-Bearer header
    # with 401 + WWW-Authenticate: Bearer.
    bearer = HTTPBearer()

    def check(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> None:
        try:
            jwt.decode(
                credentials.credentials,
                public_key,
                algorithms=[ALGORITHM],
                audience=AUDIENCE,
                issuer=ISSUER,
                leeway=LEEWAY_SECONDS,
                options={"require": ["iss", "sub", "aud", "iat", "exp"]},
            )
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    return check
