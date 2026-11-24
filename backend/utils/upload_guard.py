"""Checks multipart uploads before their body is read.

FastAPI reads and spools a multipart body (to memory or a temporary file)
before the route's dependencies run, so the usual `Depends(get_current_user)`
check comes too late to stop an anonymous client from streaming an endless
upload onto the server's disk. This ASGI middleware runs first:

* a multipart request must carry a valid access token in the Authorization
  header, otherwise it is answered with 401 without reading the body;
* the body may not exceed `MAX_UPLOAD_MB` (default 500 MB, the same limit
  nginx applies in the Docker setup); larger requests get 413.

Backup restores (`/api/admin/restore`) are exempt from the size limit
because a full backup can be larger, but still need a valid token.
"""

from __future__ import annotations

import json
import os

from fastapi import HTTPException

from dependencies.auth import decode_token

MAX_UPLOAD_BYTES = max(1, int(os.getenv("MAX_UPLOAD_MB", "500"))) * 1024 * 1024
UNLIMITED_PATHS = ("/api/admin/restore",)


class _BodyTooLarge(HTTPException):
    """413 raised while the body is read; FastAPI passes HTTPExceptions through as responses."""

    def __init__(self, limit: int):
        super().__init__(status_code=413, detail=f"The upload is larger than the {limit // (1024 * 1024)} MB limit.")


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


class UploadGuardMiddleware:
    def __init__(self, app, max_bytes: int = MAX_UPLOAD_BYTES, unlimited_paths=UNLIMITED_PATHS):
        self.app = app
        self.max_bytes = max_bytes
        self.unlimited_paths = tuple(unlimited_paths)

    async def __call__(self, scope, receive, send):
        if (
            scope.get("type") != "http"
            or scope.get("method") not in ("POST", "PUT", "PATCH")
            or not _header(scope, b"content-type").lower().startswith("multipart/form-data")
        ):
            await self.app(scope, receive, send)
            return

        auth = _header(scope, b"authorization")
        token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
        try:
            decode_token(token, expected_type="access")
        except HTTPException:
            await _reply(send, 401, "Not authenticated")
            return

        path = scope.get("path") or ""
        limit = None if path in self.unlimited_paths else self.max_bytes
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared = _header(scope, b"content-length")
        if declared.isdigit() and int(declared) > limit:
            await _reply(send, 413, f"The upload is larger than the {limit // (1024 * 1024)} MB limit.")
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
