"""Checks request bodies before they are read.

FastAPI reads a request body (JSON into memory, multipart into a spooled
temporary file) before the route's dependencies run, so the usual
`Depends(get_current_user)` check comes too late to stop an anonymous client
from streaming an endless body into memory or onto the server's disk. This ASGI
middleware runs first:

* every POST/PUT/PATCH body is limited: `MAX_REQUEST_MB` (default 20 MB) for
  ordinary requests such as JSON, `MAX_UPLOAD_MB` (default 500 MB, the same limit
  nginx applies in the Docker setup) for multipart uploads; larger bodies get 413;
* a multipart upload must carry a valid access token for an existing user whose
  password has not changed since the token was issued, otherwise it is answered
  with 401 before any of the body is read;
* backup restores (`/api/admin/restore`) need an admin account and are exempt
  from the upload size limit, because a full backup can be larger.
"""

from __future__ import annotations

import json
import os

from fastapi import HTTPException

MAX_UPLOAD_BYTES = max(1, int(os.getenv("MAX_UPLOAD_MB", "500"))) * 1024 * 1024
MAX_REQUEST_BYTES = max(1, int(os.getenv("MAX_REQUEST_MB", "20"))) * 1024 * 1024
ADMIN_UPLOAD_PATHS = ("/api/admin/restore",)


class _BodyTooLarge(HTTPException):
    """413 raised while the body is read; FastAPI passes HTTPExceptions through as responses."""

    def __init__(self, limit: int):
        super().__init__(status_code=413, detail=_too_large(limit))


def _too_large(limit: int) -> str:
    return f"The request is larger than the {max(1, limit // (1024 * 1024))} MB limit."


def _header(scope, name: bytes) -> str:
    for key, value in scope.get("headers") or ():
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


async def _reply(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
    })
    await send({"type": "http.response.body", "body": body})


async def _uploader(token: str):
    """The user behind a still-valid access token, or None."""
    from database import AsyncSessionLocal
    from dependencies.auth import decode_token, token_matches_user
    from models.user import User

    try:
        payload = decode_token(token, expected_type="access")
    except HTTPException:
        return None
    async with AsyncSessionLocal() as db:
        user = await db.get(User, payload["sub"])
    if user is None or not token_matches_user(payload, user):
        return None
    return user


class UploadGuardMiddleware:
    def __init__(
        self,
        app,
        max_upload_bytes: int = MAX_UPLOAD_BYTES,
        max_request_bytes: int = MAX_REQUEST_BYTES,
        admin_paths=ADMIN_UPLOAD_PATHS,
        authenticate=_uploader,
    ):
        self.app = app
        self.max_upload_bytes = max_upload_bytes
        self.max_request_bytes = max_request_bytes
        self.admin_paths = tuple(admin_paths)
        self.authenticate = authenticate

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        limit: int | None = self.max_request_bytes
        if _header(scope, b"content-type").lower().startswith("multipart/form-data"):
            auth = _header(scope, b"authorization")
            token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
            user = await self.authenticate(token) if token else None
            if user is None:
                await _reply(send, 401, "Not authenticated")
                return
            if (scope.get("path") or "") in self.admin_paths:
                if not getattr(user, "is_admin", False):
                    await _reply(send, 403, "Admin access required")
                    return
                limit = None
            else:
                limit = self.max_upload_bytes

        if limit is None:
            await self.app(scope, receive, send)
            return

        declared = _header(scope, b"content-length")
        if declared.isdigit() and int(declared) > limit:
            await _reply(send, 413, _too_large(limit))
            return

        received = 0
        started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body") or b"")
                if received > limit:
                    raise _BodyTooLarge(limit)
            return message

        async def tracking_send(message):
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge as exc:
            if not started:
                await _reply(send, 413, exc.detail)
