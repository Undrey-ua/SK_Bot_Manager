from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Brand, Client, Sale, User, UserRole
from database.repositories.base import BaseRepository


class SaleRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    def _detail_options(self):
        return (
            selectinload(Sale.manager).selectinload(User.supervisor),
            selectinload(Sale.client).selectinload(Client.region),
            selectinload(Sale.brand),
        )

    @staticmethod
    def _manager_scope(manager_id: int):
        """Продажі регіонального менеджера і його менеджерів зі збуту."""
        team = select(User.id).where(
            User.role == UserRole.SALES_MANAGER.value,
            User.supervisor_id == manager_id,
        )
        return or_(Sale.manager_id == manager_id, Sale.manager_id.in_(team))

    async def create(
        self,
        *,
        manager_id: int,
        client_id: int,
        brand_id: int,
        quantity: Decimal,
        sold_at: date,
        comment: str | None,
        from_swatch: bool = False,
    ) -> Sale:
        sale = Sale(
            manager_id=manager_id,
            client_id=client_id,
            brand_id=brand_id,
            quantity=quantity,
            sold_at=sold_at,
            comment=comment,
            from_swatch=from_swatch,
        )
        self._session.add(sale)
        await self._session.flush()
        return sale

    async def list_between(
        self,
        start: date,
        end: date,
        *,
        manager_id: int | None = None,
    ) -> list[Sale]:
        stmt = (
            select(Sale)
            .where(Sale.sold_at >= start, Sale.sold_at < end)
            .options(*self._detail_options())
            .order_by(Sale.sold_at.desc(), Sale.id.desc())
        )
        if manager_id is not None:
            stmt = stmt.where(self._manager_scope(manager_id))
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def sum_quantity_between(
        self,
        start: date,
        end: date,
        *,
        manager_id: int | None = None,
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(Sale.quantity), 0)).where(
            Sale.sold_at >= start,
            Sale.sold_at < end,
        )
        if manager_id is not None:
            stmt = stmt.where(self._manager_scope(manager_id))
        result = await self._session.execute(stmt)
        return Decimal(str(result.scalar_one()))

    async def sum_quantity_by_manager_between(
        self,
        start: date,
        end: date,
    ) -> dict[int, Decimal]:
        credited_id = case(
            (
                and_(
                    User.role == UserRole.SALES_MANAGER.value,
                    User.supervisor_id.is_not(None),
                ),
                User.supervisor_id,
            ),
            else_=Sale.manager_id,
        )
        stmt = (
            select(credited_id, func.coalesce(func.sum(Sale.quantity), 0))
            .join(User, User.id == Sale.manager_id)
            .where(Sale.sold_at >= start, Sale.sold_at < end)
            .group_by(credited_id)
        )
        result = await self._session.execute(stmt)
        return {row[0]: Decimal(str(row[1])) for row in result.all()}

    async def list_for_client_between(
        self,
        client_id: int,
        start: date,
        end: date,
        *,
        brand_id: int | None = None,
    ) -> list[Sale]:
        stmt = (
            select(Sale)
            .where(
                Sale.client_id == client_id,
                Sale.sold_at >= start,
                Sale.sold_at < end,
            )
            .options(*self._detail_options())
            .order_by(Sale.sold_at.desc(), Sale.id.desc())
        )
        if brand_id is not None:
            stmt = stmt.where(Sale.brand_id == brand_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, sale_id: int) -> Sale | None:
        result = await self._session.execute(
            select(Sale).where(Sale.id == sale_id).options(*self._detail_options())
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        sale_id: int,
        *,
        client_id: int,
        brand_id: int,
        quantity: Decimal,
        sold_at: date,
        comment: str | None,
        from_swatch: bool | None = None,
    ) -> Sale | None:
        sale = await self.get_by_id(sale_id)
        if sale is None:
            return None
        sale.client_id = client_id
        sale.brand_id = brand_id
        sale.quantity = quantity
        sale.sold_at = sold_at
        sale.comment = comment
        if from_swatch is not None:
            sale.from_swatch = from_swatch
        await self._session.flush()
        return sale

    async def delete(self, sale_id: int) -> bool:
        sale = await self.get_by_id(sale_id)
        if sale is None:
            return False
        await self._session.delete(sale)
        await self._session.flush()
        return True
