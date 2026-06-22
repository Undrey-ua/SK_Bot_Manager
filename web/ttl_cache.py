"""Простий in-memory TTL-кеш для важких сторінок (один процес uvicorn)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

_store: dict[str, tuple[float, object]] = {}
DEFAULT_TTL_SECONDS = 600


def _purge_expired(now: float) -> None:
    expired = [key for key, (expires_at, _) in _store.items() if expires_at <= now]
    for key in expired:
        _store.pop(key, None)


def get_cached(key: str) -> object | None:
    now = time.monotonic()
    entry = _store.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if expires_at <= now:
        _store.pop(key, None)
        return None
    return value


def set_cached(key: str, value: object, *, ttl: int = DEFAULT_TTL_SECONDS) -> None:
    now = time.monotonic()
    if len(_store) > 256:
        _purge_expired(now)
    _store[key] = (now + ttl, value)


async def get_or_load(
    key: str,
    loader: Callable[[], Awaitable[T]],
    *,
    ttl: int = DEFAULT_TTL_SECONDS,
) -> T:
    cached = get_cached(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    value = await loader()
    set_cached(key, value, ttl=ttl)
    return value
