"""План продажів менеджерів (кв. м / місяць)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from config.team import filter_regional_managers
from database.models import User
from database.repositories.sales_plan import ManagerSalesPlanRepository
from database.repositories.sale import SaleRepository
from database.repositories.user import UserRepository
from web.analytics_periods import month_range
from web.utils import plan_progress_pct


@dataclass(frozen=True)
class SalesPlanProgress:
    manager_id: int
    manager_name: str
    target: Decimal | None
    actual: Decimal
    pct: int


class SalesPlanService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._plans = ManagerSalesPlanRepository(session)
        self._sales = SaleRepository(session)
        self._users = UserRepository(session)

    async def actual_for_manager(
        self,
        manager_id: int,
        *,
        year: int,
        month: int,
    ) -> Decimal:
        period = month_range(year, month)
        return await self._sales.sum_quantity_between(
            period.start,
            period.end,
            manager_id=manager_id,
        )

    async def progress_for_manager(
        self,
        manager_id: int,
        manager_name: str,
        *,
        year: int,
        month: int,
    ) -> SalesPlanProgress:
        plan = await self._plans.get_for_period(manager_id, year=year, month=month)
        actual = await self.actual_for_manager(manager_id, year=year, month=month)
        target = plan.target_sqm if plan else None
        return SalesPlanProgress(
            manager_id=manager_id,
            manager_name=manager_name,
            target=target,
            actual=actual,
            pct=plan_progress_pct(actual, target),
        )

    async def progress_for_all_managers(
        self,
        *,
        year: int,
        month: int,
    ) -> list[SalesPlanProgress]:
        managers = filter_regional_managers(await self._users.list_all())
        if not managers:
            return []

        period = month_range(year, month)
        plans = await self._plans.list_for_period(year=year, month=month)
        plan_by_manager = {p.manager_id: p.target_sqm for p in plans}
        actual_by_manager = await self._sales.sum_quantity_by_manager_between(
            period.start,
            period.end,
        )

        rows: list[SalesPlanProgress] = []
        for m in managers:
            target = plan_by_manager.get(m.id)
            actual = actual_by_manager.get(m.id, Decimal(0))
            rows.append(
                SalesPlanProgress(
                    manager_id=m.id,
                    manager_name=m.name,
                    target=target,
                    actual=actual,
                    pct=plan_progress_pct(actual, target),
                )
            )
        return rows

    async def plans_map_for_period(
        self,
        *,
        year: int,
        month: int,
    ) -> dict[int, Decimal]:
        plans = await self._plans.list_for_period(year=year, month=month)
        return {p.manager_id: p.target_sqm for p in plans}

    async def save_plans(
        self,
        *,
        year: int,
        month: int,
        values: dict[int, Decimal],
        created_by_id: int,
    ) -> None:
        for manager_id, target in values.items():
            if target <= 0:
                continue
            await self._plans.upsert(
                manager_id=manager_id,
                year=year,
                month=month,
                target_sqm=target,
                created_by_id=created_by_id,
            )

    async def regional_managers(self) -> list[User]:
        return filter_regional_managers(await self._users.list_all())
