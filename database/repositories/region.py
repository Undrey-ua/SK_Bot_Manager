from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ManagerRegion
from database.repositories.base import BaseRepository


class RegionRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_manager(self, manager_id: int) -> list[ManagerRegion]:
        result = await self._session.execute(
            select(ManagerRegion)
            .where(ManagerRegion.manager_id == manager_id)
            .order_by(ManagerRegion.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, region_id: int) -> ManagerRegion | None:
        result = await self._session.execute(
            select(ManagerRegion).where(ManagerRegion.id == region_id)
        )
        return result.scalar_one_or_none()

    async def create(self, manager_id: int, name: str) -> ManagerRegion:
        region = ManagerRegion(manager_id=manager_id, name=name.strip())
        self._session.add(region)
        await self._session.flush()
        return region
