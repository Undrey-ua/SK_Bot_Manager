from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Stand
from database.repositories.base import BaseRepository


class StandRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_active(self) -> list[Stand]:
        result = await self._session.execute(
            select(Stand)
            .where(Stand.is_active.is_(True))
            .order_by(Stand.sort_order, Stand.name)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[Stand]:
        result = await self._session.execute(
            select(Stand).order_by(Stand.sort_order, Stand.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, stand_id: int) -> Stand | None:
        result = await self._session.execute(
            select(Stand).where(Stand.id == stand_id)
        )
        return result.scalar_one_or_none()

    async def create(self, name: str, sort_order: int = 0) -> Stand:
        stand = Stand(name=name.strip(), sort_order=sort_order)
        self._session.add(stand)
        await self._session.flush()
        return stand

    async def set_active(self, stand_id: int, is_active: bool) -> Stand | None:
        stand = await self.get_by_id(stand_id)
        if stand is None:
            return None
        stand.is_active = is_active
        await self._session.flush()
        return stand

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(Stand))
        return int(result.scalar_one())
