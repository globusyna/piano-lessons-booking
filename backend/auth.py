import os
import secrets
import sys
from datetime import UTC, datetime, timedelta
from typing import NoReturn

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
JWT_ALGORITHM = "HS256"
JWT_TTL = timedelta(hours=8)

JWT_SECRET_VARIABLE = "PIANO_JWT_SECRET"
DEV_MODE_VARIABLE = "PIANO_DEV_MODE"
JWT_SECRET_MIN_LENGTH = 32

HOW_TO_PROCEED = f"""There are two ways to proceed.

  1. Set {JWT_SECRET_VARIABLE} to a private secret of at least {JWT_SECRET_MIN_LENGTH} characters,
     kept out of version control:

       export {JWT_SECRET_VARIABLE}="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(32))')"

  2. For local development only, set {DEV_MODE_VARIABLE}=1. The backend then generates a
     throwaway secret for each run, and every admin token stops working on restart:

       export {DEV_MODE_VARIABLE}=1"""


def _refuse_to_start(reason: str) -> NoReturn:
    print(f"{reason}\n\n{HOW_TO_PROCEED}", file=sys.stderr)
    raise SystemExit(1)


def _resolve_jwt_secret() -> str:
    """Return the key admin tokens are signed with, or refuse to start without one.

    An explicitly configured secret always wins over the development fallback.
    """
    configured = os.getenv(JWT_SECRET_VARIABLE)

    if configured is None:
        if os.getenv(DEV_MODE_VARIABLE) == "1":
            print(
                f"{DEV_MODE_VARIABLE}=1: generated a development {JWT_SECRET_VARIABLE} for this "
                "process only - admin tokens issued during this run stop working after the next "
                "restart.",
                file=sys.stderr,
            )
            return secrets.token_urlsafe(JWT_SECRET_MIN_LENGTH)
        _refuse_to_start(
            f"{JWT_SECRET_VARIABLE} is not set, so the backend cannot sign admin tokens "
            "and refuses to start."
        )

    if not configured.strip():
        _refuse_to_start(
            f"{JWT_SECRET_VARIABLE} is set but blank, so the backend cannot sign admin tokens "
            "and refuses to start."
        )

    if len(configured) < JWT_SECRET_MIN_LENGTH:
        _refuse_to_start(
            f"{JWT_SECRET_VARIABLE} is {len(configured)} characters long, below the "
            f"{JWT_SECRET_MIN_LENGTH}-character minimum, so the backend refuses to start. "
            "The minimum is a floor against placeholder and obviously short secrets, not a "
            "guarantee of entropy - use a value from a cryptographic random source."
        )

    return configured


JWT_SECRET = _resolve_jwt_secret()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def create_access_token(subject: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": subject, "iat": now, "exp": now + JWT_TTL},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHENTICATED", "message": "A valid admin token is required."},
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthenticated()
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise unauthenticated() from None
    if payload.get("sub") != "admin":
        raise unauthenticated()
    return "admin"
