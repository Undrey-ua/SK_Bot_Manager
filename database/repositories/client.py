from __future__ import annotations

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Client, ClientStand
from database.repositories.base import BaseRepository


class ClientRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    @staticmethod
    def _detail_options():
        return (
            selectinload(Client.region),
            selectinload(Client.stand_links).selectinload(ClientStand.stand),
        )

    @staticmethod
    def _admin_list_options():
        return (
            selectinload(Client.manager),
            selectinload(Client.region),
            selectinload(Client.stand_links).selectinload(ClientStand.stand),
        )

    async def list_all(self) -> list[Client]:
        result = await self._session.execute(
            select(Client)
            .options(*self._admin_list_options())
            .order_by(Client.name)
        )
        return list(result.scalars().all())

    async def list_by_manager(self, manager_id: int) -> list[Client]:
        result = await self._session.execute(
            select(Client)
            .where(Client.manager_id == manager_id)
            .options(*self._detail_options())
            .order_by(Client.name)
        )
        return list(result.scalars().all())

    async def list_by_manager_and_region(
        self,
        manager_id: int,
        region_id: int,
    ) -> list[Client]:
        result = await self._session.execute(
            select(Client)
            .where(
                Client.manager_id == manager_id,
                Client.region_id == region_id,
            )
            .options(*self._detail_options())
            .order_by(Client.name)
        )
        return list(result.scalars().all())

    def _apply_filters(
        self,
        stmt,
        *,
        manager_id: int | None = None,
        region_id: int | None = None,
        city: str | None = None,
        stand_id: int | None = None,
    ):
        if manager_id is not None:
            stmt = stmt.where(Client.manager_id == manager_id)
        if region_id is not None:
            stmt = stmt.where(Client.region_id == region_id)
        if city:
            stmt = stmt.where(Client.city == city)
        if stand_id is not None:
            stmt = stmt.where(
                exists().where(
                    ClientStand.client_id == Client.id,
                    ClientStand.stand_id == stand_id,
                )
            )
        return stmt

    async def count_filtered(
        self,
        *,
        manager_id: int | None = None,
        region_id: int | None = None,
        city: str | None = None,
        stand_id: int | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(Client),
            manager_id=manager_id,
            region_id=region_id,
            city=city,
            stand_id=stand_id,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_filtered(
        self,
        *,
        manager_id: int | None = None,
        region_id: int | None = None,
        city: str | None = None,
        stand_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Client]:
        stmt = self._apply_filters(
            select(Client).options(*self._admin_list_options()).order_by(Client.name),
            manager_id=manager_id,
            region_id=region_id,
            city=city,
            stand_id=stand_id,
        )
        result = await self._session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all())

    async def list_for_filter_options(
        self,
        *,
        manager_id: int | None = None,
    ) -> list[Client]:
        stmt = (
            select(Client)
            .options(
                selectinload(Client.manager),
                selectinload(Client.region),
            )
            .order_by(Client.name)
        )
        if manager_id is not None:
            stmt = stmt.where(Client.manager_id == manager_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, client_id: int) -> Client | None:
        result = await self._session.execute(
            select(Client)
            .where(Client.id == client_id)
            .options(*self._detail_options())
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_manager(self, client_id: int) -> Client | None:
        result = await self._session.execute(
            select(Client)
            .where(Client.id == client_id)
            .options(*self._admin_list_options())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        manager_id: int,
        region_id: int,
        name: str,
        address: str,
        comment: str | None,
        stand_ids: list[int],
        *,
        city: str | None = None,
        contacts: str | None = None,
        photo_url: str | None = None,
    ) -> Client:
        client = Client(
            manager_id=manager_id,
            region_id=region_id,
            name=name.strip(),
            address=address.strip(),
            city=city.strip() if city else None,
            comment=comment,
            contacts=contacts,
            photo_url=photo_url,
        )
        self._session.add(client)
        await self._session.flush()
        for stand_id in stand_ids:
            self._session.add(
                ClientStand(client_id=client.id, stand_id=stand_id, quantity=1)
            )
        await self._session.flush()
        return await self.get_by_id(client.id)  # type: ignore[return-value]

    async def update(
        self,
        client_id: int,
        region_id: int,
        name: str,
        address: str,
        comment: str | None,
        stand_ids: list[int],
        stand_qty: dict[int, int] | None = None,
        *,
        city: str | None = None,
        contacts: str | None = None,
        photo_url: str | None = None,
        update_photo: bool = False,
    ) -> Client | None:
        client = await self.get_by_id(client_id)
        if client is None:
            return None

        client.region_id = region_id
        client.name = name.strip()
        client.address = address.strip()
        client.city = city.strip() if city else None
        client.comment = comment
        client.contacts = contacts
        if update_photo:
            client.photo_url = photo_url

        client.stand_links.clear()
        await self._session.flush()
        qty_map = stand_qty or {}
        for stand_id in stand_ids:
            qty = max(1, int(qty_map.get(stand_id, 1)))
            self._session.add(
                ClientStand(client_id=client.id, stand_id=stand_id, quantity=qty)
            )
        await self._session.flush()
        return await self.get_by_id(client.id)
