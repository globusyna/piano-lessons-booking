from fastapi import APIRouter, HTTPException, status

from ..auth import create_access_token, verify_password
from ..models import LoginRequest, TokenResponse
from ..store import store


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/token", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    valid = body.username == store.admin_username and verify_password(
        body.password, store.admin_password_hash
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "Incorrect username or password."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(accessToken=create_access_token("admin"))
