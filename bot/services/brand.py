from __future__ import annotations

from database.models import Brand, Client
from database.repositories.brand import BrandRepository
from bot.utils.client_brands import (
    brands_for_client,
    is_big_stand,
    stand_covered_by_brands,
    _brand_for_stand_name,
)
from utils.stand_brand_match import stand_matches_brand


class BrandService:
    def __init__(self, repo: BrandRepository) -> None:
        self._repo = repo

    async def list_active(self) -> list[Brand]:
        return await self._repo.list_active()

    async def list_all(self) -> list[Brand]:
        return await self._repo.list_all()

    async def get_by_id(self, brand_id: int) -> Brand | None:
        return await self._repo.get_by_id(brand_id)

    async def _resolve_brand_for_stand(self, stand_name: str) -> Brand | None:
        if is_big_stand(stand_name):
            return None
        all_brands = await self._repo.list_all()
        matched = _brand_for_stand_name(stand_name, all_brands)
        if matched:
            return matched
        for brand in all_brands:
            if stand_matches_brand(stand_name, brand.name):
                return brand
        existing = await self._repo.get_by_name(stand_name)
        if existing:
            return existing
        return await self._repo.create(stand_name)

    async def brands_for_client_stands(self, client: Client) -> list[Brand]:
        """Бренди для продажу: за стендами клієнта + автостворення ТМ для нових стендів."""
        active = await self.list_active()
        result = brands_for_client(client, active)
        seen = {b.id for b in result}

        for link in client.stand_links:
            stand = link.stand
            if stand is None or not stand.is_active:
                continue
            if stand_covered_by_brands(stand.name, result):
                continue
            brand = await self._resolve_brand_for_stand(stand.name)
            if brand and brand.id not in seen:
                result.append(brand)
                seen.add(brand.id)

        return sorted(result, key=lambda b: (b.sort_order, b.name))
