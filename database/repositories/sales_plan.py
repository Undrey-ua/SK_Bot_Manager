from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ManagerSalesPlan
from database.repositories.base import BaseRepository


class ManagerSalesPlanRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_for_period(
        self,
        manager_id: int,
        *,
        year: int,
        month: int,
    ) -> ManagerSalesPlan | None:
        result = await self._session.execute(
            select(ManagerSalesPlan).where(
                ManagerSalesPlan.manager_id == manager_id,
                ManagerSalesPlan.year == year,
                ManagerSalesPlan.month == month,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_period(
        self,
        *,
        year: int,
        month: int,
    ) -> list[ManagerSalesPlan]:
        result = await self._session.execute(
            select(ManagerSalesPlan)
            .where(
                ManagerSalesPlan.year == year,
                ManagerSalesPlan.month == month,
            )
            .order_by(ManagerSalesPlan.manager_id)
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        *,
        manager_id: int,
        year: int,
        month: int,
        target_sqm: Decimal,
        created_by_id: int,
    ) -> ManagerSalesPlan:
        row = await self.get_for_period(manager_id, year=year, month=month)
        if row is None:
            row = ManagerSalesPlan(
                manager_id=manager_id,
                year=year,
                month=month,
                target_sqm=target_sqm,
                created_by_id=created_by_id,
            )
            self._session.add(row)
        else:
            row.target_sqm = target_sqm
            row.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return row
