import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
JWT_ALGORITHM = "HS256"
JWT_TTL = timedelta(hours=8)
JWT_SECRET = os.getenv("PIANO_JWT_SECRET", "local-development-secret-change-me")


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
