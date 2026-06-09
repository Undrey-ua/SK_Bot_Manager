from __future__ import annotations

from database.models import Stand
from database.repositories.stand import StandRepository
from database.seed import DEFAULT_STANDS


class StandService:
    def __init__(self, repo: StandRepository) -> None:
        self._repo = repo

    async def list_active(self) -> list[Stand]:
        return await self._repo.list_active()

    async def list_all(self) -> list[Stand]:
        return await self._repo.list_all()

    async def create(self, name: str) -> Stand:
        stands = await self._repo.list_all()
        return await self._repo.create(name, sort_order=len(stands) + 1)

    async def set_active(self, stand_id: int, is_active: bool) -> Stand | None:
        return await self._repo.set_active(stand_id, is_active)

    async def seed_defaults(self) -> None:
        if await self._repo.count() > 0:
            return
        for index, name in enumerate(DEFAULT_STANDS, start=1):
            await self._repo.create(name, sort_order=index)
