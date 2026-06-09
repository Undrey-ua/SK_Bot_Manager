#!/usr/bin/env python3
"""Застосувати один або кілька SQL-файлів міграцій до БД з .env."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import get_settings
from database.session import create_engine


def _statements(sql: str) -> list[str]:
    parts: list[str] = []
    for chunk in sql.split(";"):
        lines = [
            ln for ln in chunk.splitlines() if ln.strip() and not ln.strip().startswith("--")
        ]
        if lines:
            parts.append("\n".join(lines))
    return parts


async def apply_file(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    settings = get_settings()
    engine = create_engine(settings.database_url)
    stmts = _statements(sql)
    async with engine.begin() as conn:
        for stmt in stmts:
            await conn.execute(text(stmt))
    await engine.dispose()
    print(f"OK: {path.name} ({len(stmts)} statement(s))")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply SQL migration file(s)")
    parser.add_argument(
        "files",
        nargs="*",
        help="Migration paths (default: 011_user_roles_supervisor.sql)",
    )
    args = parser.parse_args()
    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        paths = [ROOT / "database/migrations/011_user_roles_supervisor.sql"]
    for p in paths:
        if not p.is_file():
            print(f"Not found: {p}", file=sys.stderr)
            sys.exit(1)
        asyncio.run(apply_file(p))


if __name__ == "__main__":
    main()
