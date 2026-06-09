from __future__ import annotations

from database.models import ManagerRegion
from database.repositories.region import RegionRepository


class RegionService:
    def __init__(self, repo: RegionRepository) -> None:
        self._repo = repo

    async def list_by_manager(self, manager_id: int) -> list[ManagerRegion]:
        return await self._repo.list_by_manager(manager_id)

    async def get_by_id(self, region_id: int) -> ManagerRegion | None:
        return await self._repo.get_by_id(region_id)

    async def create(self, manager_id: int, name: str) -> ManagerRegion:
        return await self._repo.create(manager_id, name)
