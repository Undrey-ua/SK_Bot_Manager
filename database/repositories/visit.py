from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Client, Visit, VisitPhoto, VisitTask
from database.repositories.base import BaseRepository


class VisitRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    def _list_query(
        self,
        *,
        manager_id: int | None = None,
        client_id: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ):
        stmt = select(Visit).options(
            selectinload(Visit.manager),
            selectinload(Visit.client).selectinload(Client.region),
            selectinload(Visit.tasks),
            selectinload(Visit.photos),
        )
        if manager_id is not None:
            stmt = stmt.where(Visit.manager_id == manager_id)
        if client_id is not None:
            stmt = stmt.where(Visit.client_id == client_id)
        if start_at is not None:
            stmt = stmt.where(Visit.created_at >= start_at)
        if end_at is not None:
            stmt = stmt.where(Visit.created_at < end_at)
        return stmt.order_by(Visit.created_at.desc())

    async def list_recent(
        self,
        *,
        manager_id: int | None = None,
        client_id: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int | None = 50,
        offset: int = 0,
    ) -> list[Visit]:
        stmt = self._list_query(
            manager_id=manager_id,
            client_id=client_id,
            start_at=start_at,
            end_at=end_at,
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_client(self, client_id: int) -> list[Visit]:
        result = await self._session.execute(self._list_query(client_id=client_id))
        return list(result.scalars().all())

    async def count_by_client(self, client_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Visit).where(Visit.client_id == client_id)
        )
        return int(result.scalar_one())

    async def count(
        self,
        *,
        manager_id: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Visit)
        if manager_id is not None:
            stmt = stmt.where(Visit.manager_id == manager_id)
        if start_at is not None:
            stmt = stmt.where(Visit.created_at >= start_at)
        if end_at is not None:
            stmt = stmt.where(Visit.created_at < end_at)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def stats_summary(
        self,
        *,
        start_of_day,
        start_of_week,
        manager_id: int | None = None,
    ) -> tuple[int, int, int]:
        """total, today, week — один запит до БД."""
        stmt = select(
            func.count(),
            func.count().filter(Visit.created_at >= start_of_day),
            func.count().filter(Visit.created_at >= start_of_week),
        ).select_from(Visit)
        if manager_id is not None:
            stmt = stmt.where(Visit.manager_id == manager_id)
        result = await self._session.execute(stmt)
        total, today, week = result.one()
        return int(total), int(today), int(week)

    async def count_since(self, since: datetime, *, manager_id: int | None = None) -> int:
        stmt = select(func.count()).select_from(Visit).where(Visit.created_at >= since)
        if manager_id is not None:
            stmt = stmt.where(Visit.manager_id == manager_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def get_by_id(self, visit_id: int) -> Visit | None:
        result = await self._session.execute(
            self._list_query().where(Visit.id == visit_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        manager_id: int,
        client_id: int,
        visit_type: str,
        comment: str | None,
        tasks: list[str],
        photo_urls: list[str],
    ) -> Visit:
        visit = Visit(
            manager_id=manager_id,
            client_id=client_id,
            visit_type=visit_type,
            comment=comment,
        )
        self._session.add(visit)
        await self._session.flush()

        for task in tasks:
            self._session.add(VisitTask(visit_id=visit.id, task=task))

        for url in photo_urls:
            self._session.add(VisitPhoto(visit_id=visit.id, photo_url=url))

        await self._session.flush()
        return visit
