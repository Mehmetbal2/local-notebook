import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import PyJWTError as JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.database import get_db
from models.user import User

logger = logging.getLogger(__name__)

# Values that shipped in the repository or in the example .env. A JWT signed with one of
# these is forgeable by anyone who has seen the source, so they are never used as-is.
_INSECURE_SECRET_KEYS = {
    "change-me-in-production",
    "local-notebook-universal-secret-key-change-in-production",
    "please-change-this-in-production",
}
# A configured key shorter than this is treated like a placeholder.
_MIN_SECRET_KEY_LENGTH = 32


def _is_usable_secret_key(value: str) -> bool:
    return len(value) >= _MIN_SECRET_KEY_LENGTH and value not in _INSECURE_SECRET_KEYS


def _load_or_create_secret_key() -> str:
    """Return a usable signing key, persisting a generated one under the data dir.

    A key generated here survives restarts (otherwise every restart would invalidate all
    sessions). An explicitly configured, non-placeholder SECRET_KEY always wins.
    """
    env_value = (os.getenv("SECRET_KEY") or "").strip()
    if _is_usable_secret_key(env_value):
        return env_value
    if env_value:
        logger.warning(
            "Ignoring SECRET_KEY from the environment: it is a known placeholder or shorter than %d characters.",
            _MIN_SECRET_KEY_LENGTH,
        )

    from paths import get_data_dir

    key_path = get_data_dir() / "secret_key"
    try:
        if key_path.exists():
            stored = key_path.read_text(encoding="utf-8").strip()
            if stored:
                return stored
        import secrets

        generated = secrets.token_urlsafe(48)
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(generated + "\n")
        logger.warning(
            "SECRET_KEY was missing or an insecure placeholder; generated a persistent key at %s. "
            "Existing sign-ins are invalidated once.",
            key_path,
        )
        return generated
    except Exception:
        logger.exception("Could not persist a SECRET_KEY; using a temporary key for this run")
        import secrets

        return secrets.token_urlsafe(48)


SECRET_KEY = _load_or_create_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
REFRESH_TOKEN_EXPIRE_DAYS = 30
# Media tokens go in <img>/<audio> URLs (?token=...), which end up in browser history and
# access logs. They are short-lived and accepted only by the file/audio preview routes,
# never as a general API credential.
MEDIA_TOKEN_EXPIRE_MINUTES = int(os.getenv("MEDIA_TOKEN_EXPIRE_MINUTES", "720"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    refresh: bool = False,
) -> str:
    payload = data.copy()
    payload["type"] = "refresh" if refresh else "access"
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    elif refresh:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["exp"] = expire
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def password_fingerprint(password_hash: str) -> str:
    """A keyed fingerprint of the stored password hash, carried in every token.

    When a password is changed or reset the fingerprint changes, so every
    access and refresh token issued before that stops working at once.
    """
    digest = hmac.new(SECRET_KEY.encode("utf-8"), (password_hash or "").encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:24]


def token_payload_for(user: User) -> dict:
    return {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "pwv": password_fingerprint(user.password_hash),
    }


def create_media_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "pwv": password_fingerprint(user.password_hash),
        "type": "media",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=MEDIA_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def token_matches_user(payload: dict, user: User) -> bool:
    claim = payload.get("pwv")
    if not isinstance(claim, str):
        return False
    return hmac.compare_digest(claim, password_fingerprint(user.password_hash))


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")
        if user_id is None or token_type != expected_type:
            raise _credentials_exc
    except JWTError:
        raise _credentials_exc
    return payload


async def _get_user_from_token(
    token: str,
    db: AsyncSession,
    expected_type: str = "access",
) -> User:
    payload = decode_token(token, expected_type=expected_type)
    user = await db.get(User, payload["sub"])
    if not user or not token_matches_user(payload, user):
        raise _credentials_exc
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await _get_user_from_token(token, db)


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def get_current_user_query_or_header(
    header_token: Optional[str] = Depends(_optional_oauth2),
    query_token: Optional[str] = Query(default=None, alias="token"),
    db: AsyncSession = Depends(get_db),
) -> User:
    if header_token:
        return await _get_user_from_token(header_token, db)
    if query_token:
        # Only a short-lived media token is accepted in the URL, never a full access token.
        return await _get_user_from_token(query_token, db, expected_type="media")
    raise _credentials_exc
