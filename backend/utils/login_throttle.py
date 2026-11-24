"""Limits repeated failed sign-in attempts (in memory, per backend process).

Each failed password for the same user name from the same address counts
against that pair; after LOGIN_MAX_FAILURES failures within the window, further
attempts are refused with 429 until the window passes. A looser per-address
limit stops one client from trying many user names, and a per-user-name limit
that ignores the address stops guessing one account from many (or spoofed)
addresses. A successful sign-in clears the counter for that pair.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import deque

LOGIN_MAX_FAILURES = max(1, int(os.getenv("LOGIN_MAX_FAILURES", "10")))
LOGIN_MAX_FAILURES_PER_ADDRESS = max(LOGIN_MAX_FAILURES, int(os.getenv("LOGIN_MAX_FAILURES_PER_ADDRESS", "50")))
LOGIN_MAX_FAILURES_PER_USER = max(LOGIN_MAX_FAILURES, int(os.getenv("LOGIN_MAX_FAILURES_PER_USER", "30")))
LOGIN_WINDOW_SECONDS = max(1, int(os.getenv("LOGIN_WINDOW_SECONDS", "900")))
_MAX_TRACKED_KEYS = 10000


class LoginThrottle:
    def __init__(
        self,
        max_failures: int = LOGIN_MAX_FAILURES,
        max_per_address: int = LOGIN_MAX_FAILURES_PER_ADDRESS,
        window: int = LOGIN_WINDOW_SECONDS,
        clock=time.monotonic,
        max_per_user: int | None = None,
    ):
        self.max_failures = max_failures
        self.max_per_address = max_per_address
        self.max_per_user = max(max_failures, max_per_user if max_per_user is not None else LOGIN_MAX_FAILURES_PER_USER)
        self.window = window
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._calls = 0

    @staticmethod
    def _name(username: str) -> str:
        # A fixed-size digest, so a long user name cannot make the keys themselves large.
        return hashlib.sha256((username or "").strip().lower().encode("utf-8")).hexdigest()[:32]

    @classmethod
    def _pair(cls, address: str, username: str) -> str:
        return f"{address[:64]}\x00{cls._name(username)}"

    @classmethod
    def _user(cls, username: str) -> str:
        return f"\x01user\x00{cls._name(username)}"

    def _limits(self, address: str, username: str):
        return (
            (self._pair(address, username), self.max_failures),
            (address, self.max_per_address),
            (self._user(username), self.max_per_user),
        )

    def _recent(self, key: str, now: float) -> deque[float]:
        bucket = self._failures.get(key)
        if bucket is None:
            return deque()
        while bucket and now - bucket[0] >= self.window:
            bucket.popleft()
        if not bucket:
            self._failures.pop(key, None)
        return bucket

    def retry_after(self, address: str, username: str) -> int:
        """Seconds to wait before another attempt is allowed; 0 when allowed now."""
        now = self._clock()
        with self._lock:
            waits = []
            for key, limit in self._limits(address, username):
                bucket = self._recent(key, now)
                if len(bucket) >= limit:
                    waits.append(int(self.window - (now - bucket[0])) + 1)
            return max(waits, default=0)

    def begin_attempt(self, address: str, username: str) -> tuple[int, float | None]:
        """Check the limits and count this attempt in one step.

        Returns (retry_after_seconds, None) when refused, or (0, stamp) when allowed.
        The attempt counts as a failure from the start, so many requests sent at
        the same moment cannot all slip past the limit while their passwords are
        still being checked; `record_success(..., stamp)` takes it back.
        """
        now = self._clock()
        with self._lock:
            waits = []
            limits = self._limits(address or "unknown", username)
            for key, limit in limits:
                bucket = self._recent(key, now)
                if len(bucket) >= limit:
                    waits.append(int(self.window - (now - bucket[0])) + 1)
            if waits:
                return max(waits), None
            self._calls += 1
            if len(self._failures) > _MAX_TRACKED_KEYS or self._calls % 256 == 0:
                for key in list(self._failures):
                    self._recent(key, now)
            for key, _ in limits:
                self._failures.setdefault(key, deque()).append(now)
            return 0, now

    def record_failure(self, address: str, username: str) -> None:
        now = self._clock()
        with self._lock:
            if len(self._failures) > _MAX_TRACKED_KEYS:
                for key in list(self._failures):
                    self._recent(key, now)
            for key, _ in self._limits(address, username):
                self._failures.setdefault(key, deque()).append(now)

    def record_success(self, address: str, username: str, stamp: float | None = None) -> None:
        """Clear the user's failures from this address and take back the attempt's own count."""
        with self._lock:
            self._failures.pop(self._pair(address, username), None)
            if stamp is not None:
                for key in (address, self._user(username)):
                    bucket = self._failures.get(key)
                    if bucket:
                        try:
                            bucket.remove(stamp)
                        except ValueError:
                            pass
                        if not bucket:
                            self._failures.pop(key, None)


login_throttle = LoginThrottle()
