from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Client, ManagerRegion, Reserve
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

    async def list_all(self) -> list[ManagerRegion]:
        result = await self._session.execute(
            select(ManagerRegion)
            .options(selectinload(ManagerRegion.manager))
            .order_by(ManagerRegion.name)
        )
        return list(result.scalars().all())

    async def usage_counts(self) -> dict[int, tuple[int, int]]:
        """region_id → (клієнти, резерви)."""
        counts: dict[int, list[int]] = {}
        client_rows = await self._session.execute(
            select(Client.region_id, func.count()).group_by(Client.region_id)
        )
        for region_id, total in client_rows.all():
            counts.setdefault(int(region_id), [0, 0])[0] = int(total)
        reserve_rows = await self._session.execute(
            select(Reserve.region_id, func.count()).group_by(Reserve.region_id)
        )
        for region_id, total in reserve_rows.all():
            counts.setdefault(int(region_id), [0, 0])[1] = int(total)
        return {region_id: (pair[0], pair[1]) for region_id, pair in counts.items()}

    async def rename(self, region: ManagerRegion, name: str) -> None:
        region.name = name.strip()
        await self._session.flush()

    async def merge(self, source: ManagerRegion, target: ManagerRegion) -> tuple[int, int]:
        clients = await self._session.execute(
            update(Client)
            .where(Client.region_id == source.id)
            .values(region_id=target.id)
        )
        reserves = await self._session.execute(
            update(Reserve)
            .where(Reserve.region_id == source.id)
            .values(region_id=target.id)
        )
        await self._session.delete(source)
        await self._session.flush()
        return int(clients.rowcount or 0), int(reserves.rowcount or 0)

    async def delete(self, region: ManagerRegion) -> None:
        await self._session.delete(region)
        await self._session.flush()
