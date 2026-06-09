from __future__ import annotations

from fastapi import Request


def query_int(
    request: Request,
    name: str,
    *,
    default: int | None = None,
) -> int | None:
    """Read optional int from query string; empty string from HTML forms → default."""
    raw = request.query_params.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


def query_str(
    request: Request,
    name: str,
    *,
    default: str | None = None,
) -> str | None:
    raw = request.query_params.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip()
