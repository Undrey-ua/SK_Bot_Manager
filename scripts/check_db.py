"""Перевірка підключення до Supabase Postgres. Запуск: python scripts/check_db.py"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import get_settings


async def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(dsn)

    print(f"User:  {parsed.username}")
    print(f"Host:  {parsed.hostname}")
    print(f"Port:  {parsed.port}")

    import asyncpg

    try:
        conn = await asyncpg.connect(dsn, statement_cache_size=0)
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        print("OK — підключення успішне")
        print(version[:80] + "...")
    except asyncpg.InvalidPasswordError:
        print("Помилка: невірний пароль БД")
        print("Supabase → Project Settings → Database → Reset database password")
    except Exception as exc:
        print(f"Помилка: {type(exc).__name__}: {exc}")
        if "Tenant or user not found" in str(exc):
            print(
                "Host не відповідає проєкту. Скопіюйте URI з Dashboard → Connect "
                "(для yjvfebhgbzpkdchvwcqp очікується aws-0-eu-west-1.pooler.supabase.com)"
            )


if __name__ == "__main__":
    asyncio.run(main())
