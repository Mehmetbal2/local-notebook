"""Error text that is safe to show to people.

Raw exception text can carry internal addresses, file paths, request bodies or
fragments of API keys echoed back by a model provider. Anything a user or the
browser sees goes through `public_error_message`, which reports only the kind of
failure; the full exception stays in the server log (Settings → System status
shows recent log errors to admins).
"""

from __future__ import annotations

import asyncio

from utils.i18n import msg as ui_msg

_CONTEXT_HINTS = (
    "context length",
    "context_length",
    "maximum context",
    "context window",
    "too many tokens",
    "prompt is too long",
    "input is too long",
    "reduce the length",
)


def _status_code(exc: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int) and 100 <= value <= 599:
        return value
    return None


def error_kind(exc: BaseException) -> str:
    """One of: timeout, connect, auth, rate_limit, context, provider, bad_request, empty, unknown."""
    names = {cls.__name__ for cls in type(exc).__mro__}
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or any("Timeout" in n for n in names):
        return "timeout"
    if isinstance(exc, ConnectionError) or names & {"ConnectError", "APIConnectionError", "ConnectionError"}:
        return "connect"
    if "APIEmptyResponseError" in names:
        return "empty"
    status = _status_code(exc)
    lowered = str(exc).lower()
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "rate_limit"
    if any(hint in lowered for hint in _CONTEXT_HINTS) and (status is None or 400 <= status < 500):
        return "context"
    if status is not None and status >= 500:
        return "provider"
    if status is not None and status >= 400:
        return "bad_request"
    return "unknown"


def public_error_message(exc: BaseException) -> str:
    """A short message in the interface language that describes the failure without its details."""
    kind = error_kind(exc)
    if kind == "bad_request":
        return ui_msg("err_bad_request", status=_status_code(exc))
    return ui_msg(f"err_{kind}")
