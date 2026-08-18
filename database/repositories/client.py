from __future__ import annotations

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Client, ClientStand, ClientSwatch
from database.repositories.base import BaseRepository


class ClientRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    @staticmethod
    def _detail_options():
        return (
            selectinload(Client.region),
            selectinload(Client.stand_links).selectinload(ClientStand.stand),
            selectinload(Client.swatch_links).selectinload(ClientSwatch.brand),
        )

    @staticmethod
    def _admin_list_options():
        return (
            selectinload(Client.manager),
            selectinload(Client.region),
            selectinload(Client.stand_links).selectinload(ClientStand.stand),
            selectinload(Client.swatch_links).selectinload(ClientSwatch.brand),
        )

    async def list_all(self, *, is_pvc: bool | None = False) -> list[Client]:
        stmt = (
            select(Client)
            .options(*self._admin_list_options())
            .order_by(Client.name)
        )
        stmt = self._apply_pvc(stmt, is_pvc)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _apply_pvc(stmt, is_pvc: bool | None):
        if is_pvc is True:
            return stmt.where(Client.is_pvc.is_(True))
        if is_pvc is False:
            return stmt.where(Client.is_pvc.is_(False))
        return stmt

    async def list_by_manager(
        self,
        manager_id: int,
        *,
        is_pvc: bool | None = False,
    ) -> list[Client]:
        stmt = (
            select(Client)
            .where(Client.manager_id == manager_id)
            .options(*self._detail_options())
            .order_by(Client.name)
        )
        stmt = self._apply_pvc(stmt, is_pvc)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_manager_and_region(
        self,
        manager_id: int,
        region_id: int,
        *,
        exclude_potential: bool = False,
        potential_only: bool = False,
        is_pvc: bool | None = False,
        city: str | None = None,
    ) -> list[Client]:
        stmt = (
            select(Client)
            .where(
                Client.manager_id == manager_id,
                Client.region_id == region_id,
            )
            .options(*self._detail_options())
            .order_by(Client.name)
        )
        stmt = self._apply_pvc(stmt, is_pvc)
        if city:
            stmt = stmt.where(func.lower(Client.city) == city.strip().casefold())
        if potential_only:
            stmt = stmt.where(Client.is_potential.is_(True))
        elif exclude_potential:
            stmt = stmt.where(Client.is_potential.is_(False))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_cities_for_region(
        self,
        manager_id: int,
        region_id: int,
        *,
        is_pvc: bool | None = None,
    ) -> list[str]:
        stmt = (
            select(Client.city)
            .where(
                Client.manager_id == manager_id,
                Client.region_id == region_id,
                Client.city.is_not(None),
                Client.city != "",
            )
            .distinct()
            .order_by(Client.city)
        )
        stmt = self._apply_pvc(stmt, is_pvc)
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all() if row[0]]

    def _apply_filters(
        self,
        stmt,
        *,
        manager_id: int | None = None,
        region_id: int | None = None,
        city: str | None = None,
        stand_id: int | None = None,
        is_potential: bool | None = None,
        is_pvc: bool | None = False,
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
        if is_potential is not None:
            stmt = stmt.where(Client.is_potential.is_(is_potential))
        stmt = self._apply_pvc(stmt, is_pvc)
        return stmt

    async def count_filtered(
        self,
        *,
        manager_id: int | None = None,
        region_id: int | None = None,
        city: str | None = None,
        stand_id: int | None = None,
        is_potential: bool | None = None,
        is_pvc: bool | None = False,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(Client),
            manager_id=manager_id,
            region_id=region_id,
            city=city,
            stand_id=stand_id,
            is_potential=is_potential,
            is_pvc=is_pvc,
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
        is_potential: bool | None = None,
        is_pvc: bool | None = False,
        limit: int | None = 50,
        offset: int = 0,
    ) -> list[Client]:
        stmt = self._apply_filters(
            select(Client)
            .options(*self._admin_list_options())
            .order_by(Client.is_potential.desc(), Client.name),
            manager_id=manager_id,
            region_id=region_id,
            city=city,
            stand_id=stand_id,
            is_potential=is_potential,
            is_pvc=is_pvc,
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_filter_options(
        self,
        *,
        manager_id: int | None = None,
        is_potential: bool | None = None,
        is_pvc: bool | None = False,
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
        if is_potential is not None:
            stmt = stmt.where(Client.is_potential.is_(is_potential))
        stmt = self._apply_pvc(stmt, is_pvc)
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
        legal_name: str | None = None,
        contacts: str | None = None,
        photo_url: str | None = None,
        swatch_brand_ids: list[int] | None = None,
        is_potential: bool = False,
        is_pvc: bool = False,
    ) -> Client:
        client = Client(
            manager_id=manager_id,
            region_id=region_id,
            name=name.strip(),
            legal_name=legal_name.strip() if legal_name else None,
            address=address.strip(),
            city=city.strip() if city else None,
            comment=comment,
            contacts=contacts,
            photo_url=photo_url,
            is_potential=is_potential,
            is_pvc=is_pvc,
        )
        self._session.add(client)
        await self._session.flush()
        for stand_id in stand_ids:
            self._session.add(
                ClientStand(client_id=client.id, stand_id=stand_id, quantity=1)
            )
        for brand_id in swatch_brand_ids or []:
            self._session.add(
                ClientSwatch(client_id=client.id, brand_id=brand_id)
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
        legal_name: str | None = None,
        contacts: str | None = None,
        photo_url: str | None = None,
        update_photo: bool = False,
        swatch_brand_ids: list[int] | None = None,
        is_potential: bool | None = None,
    ) -> Client | None:
        client = await self.get_by_id(client_id)
        if client is None:
            return None

        client.region_id = region_id
        client.name = name.strip()
        client.legal_name = legal_name.strip() if legal_name else None
        client.address = address.strip()
        client.city = city.strip() if city else None
        client.comment = comment
        client.contacts = contacts
        if update_photo:
            client.photo_url = photo_url
        if is_potential is not None:
            client.is_potential = is_potential

        client.stand_links.clear()
        await self._session.flush()
        qty_map = stand_qty or {}
        for stand_id in stand_ids:
            qty = max(1, int(qty_map.get(stand_id, 1)))
            self._session.add(
                ClientStand(client_id=client.id, stand_id=stand_id, quantity=qty)
            )

        client.swatch_links.clear()
        await self._session.flush()
        for brand_id in swatch_brand_ids or []:
            self._session.add(
                ClientSwatch(client_id=client.id, brand_id=brand_id)
            )
        await self._session.flush()
        return await self.get_by_id(client.id)

    async def set_is_potential(self, client_id: int, *, is_potential: bool) -> Client | None:
        client = await self.get_by_id(client_id)
        if client is None:
            return None
        client.is_potential = is_potential
        await self._session.flush()
        return await self.get_by_id(client_id)

    async def delete(self, client_id: int) -> bool:
        exists_id = await self._session.scalar(
            select(Client.id).where(Client.id == client_id)
        )
        if exists_id is None:
            return False
        # Core DELETE — БД каскадно прибирає продажі, візити, резерви тощо.
        # ORM session.delete() намагається обнулити NOT NULL FK і падає.
        result = await self._session.execute(
            delete(Client).where(Client.id == client_id)
        )
        await self._session.flush()
        return bool(result.rowcount)
