from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Brand
from database.repositories.base import BaseRepository


class BrandRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_active(self) -> list[Brand]:
        result = await self._session.execute(
            select(Brand)
            .where(Brand.is_active.is_(True))
            .order_by(Brand.sort_order, Brand.name)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[Brand]:
        result = await self._session.execute(
            select(Brand).order_by(Brand.sort_order, Brand.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, brand_id: int) -> Brand | None:
        result = await self._session.execute(
            select(Brand).where(Brand.id == brand_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Brand | None:
        result = await self._session.execute(
            select(Brand).where(Brand.name == name.strip())
        )
        return result.scalar_one_or_none()

    async def create(self, name: str) -> Brand:
        all_brands = await self.list_all()
        brand = Brand(
            name=name.strip(),
            sort_order=len(all_brands) + 1,
            is_active=True,
        )
        self._session.add(brand)
        await self._session.flush()
        return brand
