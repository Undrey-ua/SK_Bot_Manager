from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import VisitTaskType
from database.repositories.base import BaseRepository


class VisitTaskTypeRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_all(self) -> list[VisitTaskType]:
        result = await self._session.execute(
            select(VisitTaskType).order_by(
                VisitTaskType.sort_order,
                VisitTaskType.label,
            )
        )
        return list(result.scalars().all())

    async def list_active(self) -> list[VisitTaskType]:
        result = await self._session.execute(
            select(VisitTaskType)
            .where(VisitTaskType.is_active.is_(True))
            .order_by(VisitTaskType.sort_order, VisitTaskType.label)
        )
        return list(result.scalars().all())

    async def get_by_id(self, type_id: int) -> VisitTaskType | None:
        result = await self._session.execute(
            select(VisitTaskType).where(VisitTaskType.id == type_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> VisitTaskType | None:
        result = await self._session.execute(
            select(VisitTaskType).where(VisitTaskType.code == code)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        code: str,
        label: str,
        sort_order: int = 0,
    ) -> VisitTaskType:
        row = VisitTaskType(
            code=code.strip(),
            label=label.strip(),
            sort_order=sort_order,
            is_active=True,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self,
        type_id: int,
        *,
        label: str,
        sort_order: int,
        is_active: bool,
    ) -> VisitTaskType | None:
        row = await self.get_by_id(type_id)
        if row is None:
            return None
        row.label = label.strip()
        row.sort_order = sort_order
        row.is_active = is_active
        await self._session.flush()
        return row

    async def delete(self, type_id: int) -> bool:
        row = await self.get_by_id(type_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def labels_map(self) -> dict[str, str]:
        return {row.code: row.label for row in await self.list_all()}
