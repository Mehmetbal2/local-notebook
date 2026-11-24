"""Checks for model and service addresses entered in Settings.

Connection tests and saved settings send requests to whatever address an admin
types in; that is how local and cloud model servers are configured, so the
destination itself is not restricted. What is refused is anything that is not a
plain web address: other schemes (file:, gopher:, ...), a missing host, and user
names or passwords embedded in the URL, which would otherwise be sent along and
end up in logs and error messages.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from utils.i18n import msg as ui_msg


class InvalidServiceURL(ValueError):
    pass


def checked_service_url(raw: str | None) -> str:
    """The address with surrounding whitespace removed; raises InvalidServiceURL if it is unusable."""
    value = (raw or "").strip()
    try:
        parts = urlsplit(value)
        port = parts.port  # raises ValueError for a malformed port
    except ValueError as exc:
        raise InvalidServiceURL(ui_msg("invalid_service_url")) from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise InvalidServiceURL(ui_msg("invalid_service_url"))
    if parts.username is not None or parts.password is not None:
        raise InvalidServiceURL(ui_msg("invalid_service_url_credentials"))
    if port is not None and not (0 < port < 65536):
        raise InvalidServiceURL(ui_msg("invalid_service_url"))
    return value
