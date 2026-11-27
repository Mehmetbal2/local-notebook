import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import jwt

from dependencies.auth import (
    ALGORITHM,
    MEDIA_TOKEN_EXPIRE_MINUTES,
    SECRET_KEY,
    create_media_token,
    decode_token,
    get_current_user,
    issue_tokens,
    oauth2_scheme,
    revoke_session,
    rotate_refresh,
    start_session,
    token_matches_user,
    verify_password,
)
from dependencies.database import get_db
from models.user import User
from utils.login_throttle import login_throttle
from utils.time import utc_isoformat

# Compared against when the user name does not exist, so a wrong user name costs the
# same bcrypt work as a wrong password and does not reveal which names exist.
MAX_USERNAME_LENGTH = 150
# bcrypt only reads the first 72 bytes; longer inputs only cost time.
MAX_PASSWORD_LENGTH = 1024
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
async def media_token(
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
) -> dict:
    """A short-lived token for <img>/<audio> preview URLs, which cannot carry a header."""
    sid = decode_token(token).get("sid")
    return {
        "success": True,
        "media_token": create_media_token(current_user, sid),
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
    if len(username) > MAX_USERNAME_LENGTH or len(form.password) > MAX_PASSWORD_LENGTH:
        # No account can have such a name; refuse it before it is stored as a throttle key.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    wait, attempt = login_throttle.begin_attempt(address, username)
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_throttle.record_success(address, username, attempt)

    tokens = issue_tokens(user, await start_session(db, user))
    return {
        "success": True,
        **tokens,
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
    try:
        # Each refresh token works once; reusing one revokes its session.
        session = await rotate_refresh(db, payload)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "success": True,
        **issue_tokens(user, session),
        "media_token_expires_in": MEDIA_TOKEN_EXPIRE_MINUTES * 60,
        "token_type": "bearer",
        "role": user.role,
    }


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Sign out: revoke the session of the access or refresh token sent as Bearer.

    Its access, refresh and media tokens stop working at once. Accepts an
    expired token too (only its signature is checked), so signing out works
    after the access token has run out.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = jwt.decode(auth_header[7:], SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") not in ("access", "refresh"):
        raise HTTPException(status_code=401, detail="Invalid token")
    await revoke_session(db, payload.get("sid"))
    return {"success": True}
