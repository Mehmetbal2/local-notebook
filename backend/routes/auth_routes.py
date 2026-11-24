import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import (
    MEDIA_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_media_token,
    decode_token,
    get_current_user,
    token_matches_user,
    token_payload_for,
    verify_password,
)
from dependencies.database import get_db
from models.user import User
from utils.login_throttle import login_throttle
from utils.time import utc_isoformat

# Compared against when the user name does not exist, so a wrong user name costs the
# same bcrypt work as a wrong password and does not reveal which names exist.
_DUMMY_PASSWORD_HASH = "$2b$12$a.NBm6HzKialLq2p10y7fefJG1U6Akt88VIgc4KQ2lvvGocJCb6r."

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "success": True,
        "user": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
            "created_at": utc_isoformat(current_user.created_at),
        },
        "username": current_user.username,
        "user_id": current_user.id,
        "role": current_user.role,
    }


def _check_password(plain: str, hashed: str) -> bool:
    try:
        return verify_password(plain, hashed)
    except ValueError:
        return False


@router.get("/media-token")
async def media_token(current_user: User = Depends(get_current_user)) -> dict:
    """A short-lived token for <img>/<audio> preview URLs, which cannot carry a header."""
    return {
        "success": True,
        "media_token": create_media_token(current_user),
        "expires_in": MEDIA_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/login")
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict:
    address = request.client.host if request.client else "unknown"
    username = form.username.strip()
    wait = login_throttle.retry_after(address, username)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    # bcrypt is slow on purpose; run it off the event loop so sign-ins cannot stall other requests.
    ok = await asyncio.to_thread(
        _check_password, form.password, user.password_hash if user else _DUMMY_PASSWORD_HASH
    )
    if not user or not ok:
        login_throttle.record_failure(address, username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_throttle.record_success(address, username)

    token_payload = token_payload_for(user)
    token = create_access_token(token_payload)
    refresh = create_access_token(token_payload, refresh=True)
    return {
        "success": True,
        "access_token": token,
        "refresh_token": refresh,
        "media_token": create_media_token(user),
        "media_token_expires_in": MEDIA_TOKEN_EXPIRE_MINUTES * 60,
        "token_type": "bearer",
        "username": user.username,
        "user_id": user.id,
        "role": user.role,
        "user": {
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "created_at": utc_isoformat(user.created_at),
        },
    }


@router.post("/refresh")
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    old_token = auth_header[7:]

    try:
        payload = decode_token(old_token, expected_type="refresh")
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await db.get(User, payload["sub"])
    if not user or not token_matches_user(payload, user):
        raise HTTPException(status_code=401, detail="Invalid token")

    token_payload = token_payload_for(user)
    token = create_access_token(token_payload)
    refresh = create_access_token(token_payload, refresh=True)
    return {
        "success": True,
        "access_token": token,
        "refresh_token": refresh,
        "media_token": create_media_token(user),
        "media_token_expires_in": MEDIA_TOKEN_EXPIRE_MINUTES * 60,
        "token_type": "bearer",
        "role": user.role,
    }
