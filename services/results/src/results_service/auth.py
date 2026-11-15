"""Bearer JWT check for ``PUT /results/{job_id}``.

Only the Courier's tokens (``aud: "results-service"``) get through. This
service holds only the public key, so it can verify tokens but never mint them.
Keep in step with ``analysis_service.auth``, which mints them.
"""

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ISSUER = "people-counter"
ALGORITHM = "RS256"
AUDIENCE = "results-service"
LEEWAY_SECONDS = 30


def require_courier_token():
    """A FastAPI dependency; any failure is ``401`` + ``WWW-Authenticate: Bearer``.

    It verifies with ``request.app.state.settings.jwt_public_key``.
    """
    # Its default auto_error already answers a missing or non-Bearer header
    # with 401 + WWW-Authenticate: Bearer.
    bearer = HTTPBearer()

    def check(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(bearer),
    ) -> None:
        try:
            jwt.decode(
                credentials.credentials,
                request.app.state.settings.jwt_public_key,
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
