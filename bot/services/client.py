from __future__ import annotations

from database.models import Client
from database.repositories.client import ClientRepository


class ClientService:
    def __init__(self, repo: ClientRepository) -> None:
        self._repo = repo

    async def list_by_manager(self, manager_id: int) -> list[Client]:
        return await self._repo.list_by_manager(manager_id)

    async def list_by_manager_and_region(
        self,
        manager_id: int,
        region_id: int,
        *,
        exclude_potential: bool = False,
        potential_only: bool = False,
    ) -> list[Client]:
        return await self._repo.list_by_manager_and_region(
            manager_id,
            region_id,
            exclude_potential=exclude_potential,
            potential_only=potential_only,
        )

    async def create_potential(
        self,
        manager_id: int,
        region_id: int,
        name: str,
        address: str,
        *,
        photo_url: str | None = None,
    ) -> Client:
        return await self._repo.create(
            manager_id=manager_id,
            region_id=region_id,
            name=name,
            address=address,
            comment=None,
            stand_ids=[],
            photo_url=photo_url,
            is_potential=True,
        )

    async def get_by_id(self, client_id: int) -> Client | None:
        return await self._repo.get_by_id(client_id)

    async def create(
        self,
        manager_id: int,
        region_id: int,
        name: str,
        address: str,
        comment: str | None,
        stand_ids: list[int],
        city: str | None = None,
    ) -> Client:
        return await self._repo.create(
            manager_id=manager_id,
            region_id=region_id,
            name=name,
            address=address,
            city=city,
            comment=comment,
            stand_ids=stand_ids,
        )

    async def update(
        self,
        client_id: int,
        manager_id: int,
        region_id: int,
        name: str,
        address: str,
        comment: str | None,
        stand_ids: list[int],
        city: str | None = None,
    ) -> Client | None:
        client = await self._repo.get_by_id(client_id)
        if client is None or client.manager_id != manager_id:
            return None
        return await self._repo.update(
            client_id=client_id,
            region_id=region_id,
            name=name,
            address=address,
            city=city,
            comment=comment,
            stand_ids=stand_ids,
        )
