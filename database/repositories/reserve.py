from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Client, ManagerRegion, Reserve, User
from database.repositories.base import BaseRepository


class ReserveRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    def _detail_options(self):
        return (
            selectinload(Reserve.manager),
            selectinload(Reserve.created_by),
            selectinload(Reserve.client).selectinload(Client.region),
            selectinload(Reserve.region),
        )

    async def create(
        self,
        *,
        manager_id: int,
        region_id: int,
        client_id: int,
        material: str,
        quantity: Decimal,
        created_by_id: int | None = None,
        ttl_days: int = 7,
    ) -> Reserve:
        now = datetime.now(timezone.utc)
        reserve = Reserve(
            manager_id=manager_id,
            created_by_id=created_by_id if created_by_id is not None else manager_id,
            region_id=region_id,
            client_id=client_id,
            material=material.strip(),
            quantity=quantity,
            expires_at=now + timedelta(days=ttl_days),
        )
        self._session.add(reserve)
        await self._session.flush()
        return reserve

    async def list_active(self) -> list[Reserve]:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(Reserve)
            .where(Reserve.cancelled_at.is_(None), Reserve.expires_at > now)
            .options(*self._detail_options())
            .order_by(Reserve.expires_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, reserve_id: int) -> Reserve | None:
        result = await self._session.execute(
            select(Reserve)
            .where(Reserve.id == reserve_id)
            .options(*self._detail_options())
        )
        return result.scalar_one_or_none()

    async def cancel(self, reserve_id: int) -> Reserve | None:
        reserve = await self.get_by_id(reserve_id)
        if reserve is None:
            return None
        reserve.cancelled_at = datetime.now(timezone.utc)
        await self._session.flush()
        return reserve

    async def extend(self, reserve_id: int, ttl_days: int = 7) -> Reserve | None:
        reserve = await self.get_by_id(reserve_id)
        if reserve is None:
            return None
        now = datetime.now(timezone.utc)
        base = reserve.expires_at if reserve.expires_at > now else now
        reserve.expires_at = base + timedelta(days=ttl_days)
        reserve.extended_count += 1
        reserve.expiry_notified_at = None
        await self._session.flush()
        return reserve

    async def list_expired_needing_notify(self) -> list[Reserve]:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(Reserve)
            .where(
                Reserve.cancelled_at.is_(None),
                Reserve.expires_at <= now,
                Reserve.expiry_notified_at.is_(None),
            )
            .options(*self._detail_options())
            .order_by(Reserve.expires_at.asc())
        )
        return list(result.scalars().all())

    async def mark_expiry_notified(self, reserve_id: int) -> None:
        reserve = await self.get_by_id(reserve_id)
        if reserve is None:
            return
        reserve.expiry_notified_at = datetime.now(timezone.utc)
        await self._session.flush()

