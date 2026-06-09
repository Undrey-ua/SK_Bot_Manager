"""Перенести клієнтів з чужих областей Андрія до Романа і видалити зайві області.

Запуск: .venv/bin/python scripts/fix_andrii_regions.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from config.settings import get_settings
from database.models import Client, ManagerRegion, User
from database.session import create_engine, create_session_factory

ANDRII_TG = 535827585
ROMAN_TG = 5009921383
REMOVE_FROM_ANDRII = frozenset(
    {"Дніпропетровська", "Харківська", "Запорізька", "Кіровоградська", "Одеська"}
)


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        users = {u.telegram_id: u for u in (await session.execute(select(User))).scalars()}
        andrii, roman = users[ANDRII_TG], users[ROMAN_TG]
        roman_regs = {
            r.name: r
            for r in (
                await session.execute(
                    select(ManagerRegion).where(ManagerRegion.manager_id == roman.id)
                )
            ).scalars()
        }
        andrii_regs = list(
            (
                await session.execute(
                    select(ManagerRegion).where(ManagerRegion.manager_id == andrii.id)
                )
            ).scalars()
        )
        moved = 0
        for r in andrii_regs:
            if r.name not in REMOVE_FROM_ANDRII:
                continue
            roman_r = roman_regs[r.name]
            for c in (
                await session.execute(select(Client).where(Client.region_id == r.id))
            ).scalars():
                c.manager_id = roman.id
                c.region_id = roman_r.id
                moved += 1
            await session.delete(r)
        await session.commit()
        print(f"Перенесено клієнтів: {moved}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
