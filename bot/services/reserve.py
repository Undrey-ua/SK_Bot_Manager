from __future__ import annotations

from decimal import Decimal

from database.models import Reserve
from database.repositories.reserve import ReserveRepository


class ReserveService:
    def __init__(self, repo: ReserveRepository) -> None:
        self._repo = repo

    async def create(
        self,
        *,
        manager_id: int,
        region_id: int,
        client_id: int,
        material: str,
        quantity: Decimal,
        created_by_id: int | None = None,
    ) -> Reserve:
        return await self._repo.create(
            manager_id=manager_id,
            region_id=region_id,
            client_id=client_id,
            material=material,
            quantity=quantity,
            created_by_id=created_by_id,
        )

    async def list_active(self) -> list[Reserve]:
        return await self._repo.list_active()

    async def get_by_id(self, reserve_id: int) -> Reserve | None:
        return await self._repo.get_by_id(reserve_id)

    async def cancel(self, reserve_id: int) -> Reserve | None:
        return await self._repo.cancel(reserve_id)

    async def extend(self, reserve_id: int) -> Reserve | None:
        return await self._repo.extend(reserve_id)

    async def list_expired_needing_notify(self) -> list[Reserve]:
        return await self._repo.list_expired_needing_notify()

    async def mark_expiry_notified(self, reserve_id: int) -> None:
        await self._repo.mark_expiry_notified(reserve_id)

