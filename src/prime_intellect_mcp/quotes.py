"""In-memory cache of quote tokens.

Quotes are the bridge between pod_quote (read) and pod_create (write). We keep
the *full provisioning payload* (the dict the SDK's PodsClient.create() takes)
under the token, so the create step is a single SDK call. Tokens expire after
60s to prevent stale-price provisioning."""

from __future__ import annotations

import secrets
import time
from threading import Lock
from typing import Any

QUOTE_TTL_SECONDS = 60.0


class QuoteExpired(Exception):
    """The token was issued, but TTL elapsed before the model used it."""


class QuoteUnknown(Exception):
    """The token was never issued (or was already consumed)."""


class _Cache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = Lock()

    def put(self, payload: dict[str, Any]) -> tuple[str, float]:
        token = secrets.token_urlsafe(16)
        expires_at = time.time() + QUOTE_TTL_SECONDS
        with self._lock:
            self._items[token] = (expires_at, payload)
            self._gc_locked()
        return token, expires_at

    def take(self, token: str) -> dict[str, Any]:
        with self._lock:
            self._gc_locked()
            entry = self._items.pop(token, None)
        if entry is None:
            # Either never issued or already expired-and-purged.
            raise QuoteUnknown(
                f"Quote token {token!r} is not valid. Call pod_quote again to get a fresh token."
            )
        expires_at, payload = entry
        if expires_at < time.time():
            raise QuoteExpired(
                f"Quote token expired (TTL={int(QUOTE_TTL_SECONDS)}s). Call pod_quote again."
            )
        return payload

    def peek(self, token: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._items.get(token)
        if entry is None:
            return None
        expires_at, payload = entry
        if expires_at < time.time():
            return None
        return payload

    def _gc_locked(self) -> None:
        now = time.time()
        expired = [t for t, (exp, _) in self._items.items() if exp < now]
        for t in expired:
            self._items.pop(t, None)


_cache = _Cache()


def issue_quote(payload: dict[str, Any]) -> tuple[str, float]:
    return _cache.put(payload)


def consume_quote(token: str) -> dict[str, Any]:
    return _cache.take(token)


def inspect_quote(token: str) -> dict[str, Any] | None:
    return _cache.peek(token)
