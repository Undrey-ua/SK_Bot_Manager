"""Заповнити поле clients.city з колонки «Місто» у Excel.

Запуск:
  .venv/bin/python scripts/backfill_client_cities.py --dry-run
  .venv/bin/python scripts/backfill_client_cities.py
  .venv/bin/python scripts/backfill_client_cities.py Clients_Andrii.xlsx Clients.xlsx
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from config.settings import get_settings
from database.models import Client, User
from database.session import create_engine, create_session_factory
from scripts.import_clients_xlsx import (
    SHEET_TELEGRAM,
    _norm_key,
    _read_rows,
)


def _default_xlsx_paths() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "Clients_Andrii.xlsx", root / "Clients.xlsx"]
    return [p for p in paths if p.is_file()]


async def run(paths: list[Path], *, dry_run: bool) -> int:
    records: list[dict[str, str]] = []
    for path in paths:
        records.extend(_read_rows(path))

    by_manager_name: dict[tuple[int, str], str] = {}
    for rec in records:
        city = (rec.get("city") or "").strip()
        if not city:
            continue
        manager_key = rec.get("manager_key") or ""
        telegram_id = SHEET_TELEGRAM.get(manager_key)
        if telegram_id is None:
            continue
        by_manager_name[(telegram_id, _norm_key(rec["name"]))] = city

    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)

    updated = 0
    skipped = 0
    missing = 0

    async with factory() as session:
        users = {
            u.telegram_id: u
            for u in (await session.execute(select(User))).scalars().all()
        }
        clients = list((await session.execute(select(Client))).scalars().all())

        for client in clients:
            manager = next(
                (u for u in users.values() if u.id == client.manager_id),
                None,
            )
            if manager is None:
                missing += 1
                continue

            city = by_manager_name.get((manager.telegram_id, _norm_key(client.name)))
            if not city:
                missing += 1
                continue

            current = (client.city or "").strip()
            if current == city:
                skipped += 1
                continue

            print(
                f"{'dry-run' if dry_run else 'update'}: "
                f"{manager.name} / {client.name}: {current or '—'} → {city}"
            )
            if not dry_run:
                client.city = city
            updated += 1

        if not dry_run:
            await session.commit()

    await engine.dispose()

    print()
    print(
        f"Готово: оновлено {updated}, без змін {skipped}, "
        f"не знайдено в Excel {missing}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Заповнити clients.city з Excel")
    parser.add_argument(
        "xlsx",
        nargs="*",
        type=Path,
        help="Файли Excel (за замовчуванням Clients_Andrii.xlsx і Clients.xlsx)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths = args.xlsx or _default_xlsx_paths()
    missing_files = [p for p in paths if not p.is_file()]
    if missing_files:
        for path in missing_files:
            print(f"Файл не знайдено: {path}", file=sys.stderr)
        raise SystemExit(1)

    raise SystemExit(asyncio.run(run(paths, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
