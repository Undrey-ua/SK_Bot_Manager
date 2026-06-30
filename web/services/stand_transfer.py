from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config.team import is_regional_manager
from database.models import (
    ALLOCATE_SOURCE_LABEL,
    CENTRAL_WAREHOUSE_LABEL,
    MANAGER_CENTRAL_LABEL,
    WAREHOUSE_LOCATION_LABEL,
    CentralStandStock,
    Client,
    ClientStand,
    ManagerCentralAllocation,
    ManagerRegion,
    ManagerStandStock,
    Stand,
    StandTransfer,
    StandTransferOperation,
    User,
    UserRole,
)
from database.repositories.client import ClientRepository
from database.repositories.region import RegionRepository
from database.repositories.stand import StandRepository
from database.repositories.user import UserRepository
from web.auth import WebUser
from web.roles import ORG_VIEW_ROLES, STAND_ALLOCATE_ROLES, data_owner_manager_id
from web.client_geo import client_city, client_oblast
from web.services.clients_filter import ClientFilters, filter_clients


@dataclass
class StandMoveResult:
    transfer_id: int
    to_client_id: int
    to_client_name: str


@dataclass
class StandWriteOffResult:
    transfer_id: int


@dataclass
class StandWarehouseResult:
    transfer_id: int


@dataclass
class StandAllocateResult:
    transfer_id: int


@dataclass
class WarehouseStockRow:
    stand_id: int
    stand_name: str
    quantity: int


@dataclass
class CentralOverviewRow:
    stand_id: int
    stand_name: str
    pool_quantity: int
    allocated_quantity: int
    regional_quantity: int

    @property
    def total_quantity(self) -> int:
        return self.pool_quantity + self.allocated_quantity


@dataclass
class ManagerStockOverviewRow:
    manager_id: int
    manager_name: str
    stand_id: int
    stand_name: str
    central_quantity: int
    regional_quantity: int


@dataclass
class ManagerWarehouseRow:
    stand_id: int
    stand_name: str
    central_quantity: int
    regional_quantity: int


@dataclass
class StandTransferRow:
    transfer: StandTransfer
    from_label: str
    to_label: str
    from_city: str
    to_city: str
    from_oblast: str
    to_oblast: str


class StandTransferService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._clients = ClientRepository(session)
        self._regions = RegionRepository(session)
        self._stands = StandRepository(session)
        self._users = UserRepository(session)

    async def list_clients_for_manager(self, manager_id: int) -> list[Client]:
        return await self._clients.list_by_manager(manager_id)

    async def client_has_stand(self, client_id: int, stand_id: int) -> bool:
        return self._stand_qty_on_client(
            await self._clients.get_by_id(client_id),
            stand_id,
        ) > 0

    @staticmethod
    def _stand_qty_on_client(client: Client | None, stand_id: int) -> int:
        if client is None:
            return 0
        for link in client.stand_links:
            if link.stand_id == stand_id:
                return max(1, int(getattr(link, "quantity", 1) or 1))
        return 0

    def _assert_actor_may_edit_client(self, actor: WebUser, client: Client) -> int:
        if actor.is_sales_manager or actor.is_leader:
            raise ValueError("Немає прав на операції зі стендами")
        if actor.role == UserRole.MANAGER.value and client.manager_id != actor.id:
            raise ValueError("Немає доступу до цієї торгової точки")
        return client.manager_id

    def _assert_actor_may_operate_for_manager(
        self,
        actor: WebUser,
        manager_id: int,
    ) -> None:
        if actor.is_sales_manager or actor.is_leader:
            raise ValueError("Немає прав на операції зі складом")
        if actor.role == UserRole.MANAGER.value and actor.id != manager_id:
            raise ValueError("Немає доступу до цього складу")

    def _assert_actor_may_allocate(self, actor: WebUser) -> None:
        if actor.role not in STAND_ALLOCATE_ROLES:
            raise ValueError("Немає прав на виділення стендів")

    async def _assert_field_manager_id(self, manager_id: int) -> User:
        user = await self._users.get_by_id(manager_id)
        if user is None or not is_regional_manager(user):
            raise ValueError("Оберіть регіонального менеджера")
        return user

    async def _warehouse_qty(self, manager_id: int, stand_id: int) -> int:
        result = await self._session.execute(
            select(ManagerStandStock).where(
                ManagerStandStock.manager_id == manager_id,
                ManagerStandStock.stand_id == stand_id,
            )
        )
        row = result.scalar_one_or_none()
        return max(0, int(row.quantity)) if row is not None else 0

    async def _add_warehouse_qty(
        self,
        manager_id: int,
        stand_id: int,
        qty: int,
    ) -> int:
        result = await self._session.execute(
            select(ManagerStandStock).where(
                ManagerStandStock.manager_id == manager_id,
                ManagerStandStock.stand_id == stand_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ManagerStandStock(
                manager_id=manager_id,
                stand_id=stand_id,
                quantity=qty,
            )
            self._session.add(row)
        else:
            row.quantity = int(row.quantity) + qty
        await self._session.flush()
        return int(row.quantity)

    async def _remove_warehouse_qty(
        self,
        manager_id: int,
        stand_id: int,
        qty: int,
    ) -> int:
        available = await self._warehouse_qty(manager_id, stand_id)
        if available < qty:
            raise ValueError(
                f"Недостатньо стендів на складі (є {available}, потрібно {qty})"
            )
        result = await self._session.execute(
            select(ManagerStandStock).where(
                ManagerStandStock.manager_id == manager_id,
                ManagerStandStock.stand_id == stand_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("На складі немає цього стенду")
        row.quantity = int(row.quantity) - qty
        if row.quantity <= 0:
            await self._session.delete(row)
        await self._session.flush()
        return max(0, int(row.quantity)) if row.quantity > 0 else 0

    async def _central_pool_qty(self, stand_id: int) -> int:
        result = await self._session.execute(
            select(CentralStandStock).where(CentralStandStock.stand_id == stand_id)
        )
        row = result.scalar_one_or_none()
        return max(0, int(row.quantity)) if row is not None else 0

    async def _set_central_pool_qty(self, stand_id: int, quantity: int) -> int:
        qty = max(0, int(quantity))
        result = await self._session.execute(
            select(CentralStandStock).where(CentralStandStock.stand_id == stand_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            if qty <= 0:
                return 0
            row = CentralStandStock(stand_id=stand_id, quantity=qty)
            self._session.add(row)
        else:
            row.quantity = qty
        await self._session.flush()
        return qty

    async def _sum_central_allocations(self, stand_id: int) -> int:
        result = await self._session.execute(
            select(ManagerCentralAllocation.quantity).where(
                ManagerCentralAllocation.stand_id == stand_id,
                ManagerCentralAllocation.quantity > 0,
            )
        )
        return sum(int(q) for q in result.scalars().all())

    async def _sum_regional_stock(self, stand_id: int) -> int:
        result = await self._session.execute(
            select(ManagerStandStock.quantity).where(
                ManagerStandStock.stand_id == stand_id,
                ManagerStandStock.quantity > 0,
            )
        )
        return sum(int(q) for q in result.scalars().all())

    async def _central_allocation_qty(self, manager_id: int, stand_id: int) -> int:
        result = await self._session.execute(
            select(ManagerCentralAllocation).where(
                ManagerCentralAllocation.manager_id == manager_id,
                ManagerCentralAllocation.stand_id == stand_id,
            )
        )
        row = result.scalar_one_or_none()
        return max(0, int(row.quantity)) if row is not None else 0

    async def _add_central_allocation(
        self,
        manager_id: int,
        stand_id: int,
        qty: int,
    ) -> int:
        result = await self._session.execute(
            select(ManagerCentralAllocation).where(
                ManagerCentralAllocation.manager_id == manager_id,
                ManagerCentralAllocation.stand_id == stand_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ManagerCentralAllocation(
                manager_id=manager_id,
                stand_id=stand_id,
                quantity=qty,
            )
            self._session.add(row)
        else:
            row.quantity = int(row.quantity) + qty
        await self._session.flush()
        return int(row.quantity)

    async def _remove_central_allocation(
        self,
        manager_id: int,
        stand_id: int,
        qty: int,
    ) -> int:
        available = await self._central_allocation_qty(manager_id, stand_id)
        if available < qty:
            raise ValueError(
                f"Недостатньо стендів на центральному складі менеджера "
                f"(є {available}, потрібно {qty})"
            )
        result = await self._session.execute(
            select(ManagerCentralAllocation).where(
                ManagerCentralAllocation.manager_id == manager_id,
                ManagerCentralAllocation.stand_id == stand_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("На центральному складі менеджера немає цього стенду")
        row.quantity = int(row.quantity) - qty
        if row.quantity <= 0:
            await self._session.delete(row)
        await self._session.flush()
        return max(0, int(row.quantity)) if row and row.quantity > 0 else 0

    async def _remove_central_pool_qty(self, stand_id: int, qty: int) -> int:
        available = await self._central_pool_qty(stand_id)
        if available < qty:
            raise ValueError(
                f"Недостатньо нерозподілених стендів на центральному складі "
                f"(є {available}, потрібно {qty})"
            )
        return await self._set_central_pool_qty(stand_id, available - qty)

    async def list_central_overview(self) -> list[CentralOverviewRow]:
        stands = await self._stands.list_active()
        rows: list[CentralOverviewRow] = []
        for stand in stands:
            pool = await self._central_pool_qty(stand.id)
            allocated = await self._sum_central_allocations(stand.id)
            regional = await self._sum_regional_stock(stand.id)
            rows.append(
                CentralOverviewRow(
                    stand_id=stand.id,
                    stand_name=stand.name,
                    pool_quantity=pool,
                    allocated_quantity=allocated,
                    regional_quantity=regional,
                )
            )
        return rows

    async def list_manager_central_stock(self, manager_id: int) -> list[WarehouseStockRow]:
        result = await self._session.execute(
            select(ManagerCentralAllocation)
            .where(
                ManagerCentralAllocation.manager_id == manager_id,
                ManagerCentralAllocation.quantity > 0,
            )
            .options(selectinload(ManagerCentralAllocation.stand))
            .order_by(ManagerCentralAllocation.stand_id)
        )
        rows: list[WarehouseStockRow] = []
        for item in result.scalars().all():
            if item.stand is None or not item.stand.is_active:
                continue
            rows.append(
                WarehouseStockRow(
                    stand_id=item.stand_id,
                    stand_name=item.stand.name,
                    quantity=int(item.quantity),
                )
            )
        return rows

    async def list_manager_warehouse_overview(
        self,
        manager_id: int,
    ) -> list[ManagerWarehouseRow]:
        stands = await self._stands.list_active()
        central_result = await self._session.execute(
            select(ManagerCentralAllocation).where(
                ManagerCentralAllocation.manager_id == manager_id,
            )
        )
        central_by_stand = {
            row.stand_id: max(0, int(row.quantity))
            for row in central_result.scalars().all()
        }
        regional_result = await self._session.execute(
            select(ManagerStandStock).where(
                ManagerStandStock.manager_id == manager_id,
            )
        )
        regional_by_stand = {
            row.stand_id: max(0, int(row.quantity))
            for row in regional_result.scalars().all()
        }
        return [
            ManagerWarehouseRow(
                stand_id=stand.id,
                stand_name=stand.name,
                central_quantity=central_by_stand.get(stand.id, 0),
                regional_quantity=regional_by_stand.get(stand.id, 0),
            )
            for stand in stands
        ]

    async def list_managers_stock_overview(
        self,
        manager_ids: list[int],
        manager_names: dict[int, str],
    ) -> list[ManagerStockOverviewRow]:
        if not manager_ids:
            return []
        central_result = await self._session.execute(
            select(ManagerCentralAllocation)
            .where(
                ManagerCentralAllocation.manager_id.in_(manager_ids),
                ManagerCentralAllocation.quantity > 0,
            )
            .options(selectinload(ManagerCentralAllocation.stand))
        )
        regional_result = await self._session.execute(
            select(ManagerStandStock)
            .where(
                ManagerStandStock.manager_id.in_(manager_ids),
                ManagerStandStock.quantity > 0,
            )
            .options(selectinload(ManagerStandStock.stand))
        )
        central_map: dict[tuple[int, int], int] = {}
        stand_names: dict[int, str] = {}
        for item in central_result.scalars().all():
            if item.stand is None or not item.stand.is_active:
                continue
            central_map[(item.manager_id, item.stand_id)] = int(item.quantity)
            stand_names[item.stand_id] = item.stand.name
        regional_map: dict[tuple[int, int], int] = {}
        for item in regional_result.scalars().all():
            if item.stand is None or not item.stand.is_active:
                continue
            regional_map[(item.manager_id, item.stand_id)] = int(item.quantity)
            stand_names[item.stand_id] = item.stand.name
        keys = set(central_map) | set(regional_map)
        rows: list[ManagerStockOverviewRow] = []
        for manager_id, stand_id in sorted(keys, key=lambda k: (k[0], k[1])):
            rows.append(
                ManagerStockOverviewRow(
                    manager_id=manager_id,
                    manager_name=manager_names.get(manager_id, f"#{manager_id}"),
                    stand_id=stand_id,
                    stand_name=stand_names.get(stand_id, f"#{stand_id}"),
                    central_quantity=central_map.get((manager_id, stand_id), 0),
                    regional_quantity=regional_map.get((manager_id, stand_id), 0),
                )
            )
        return rows

    async def set_central_total(
        self,
        *,
        actor: WebUser,
        stand_id: int,
        total_quantity: int,
        note: str | None = None,
    ) -> StandAllocateResult:
        self._assert_actor_may_allocate(actor)
        stand = await self._stands.get_by_id(stand_id)
        if stand is None or not stand.is_active:
            raise ValueError("Стенд не знайдено")

        total = max(0, int(total_quantity))
        allocated = await self._sum_central_allocations(stand_id)
        if total < allocated:
            raise ValueError(
                f"Загальна кількість не може бути меншою за вже розподілене "
                f"({allocated} у менеджерів)"
            )
        pool = total - allocated
        await self._set_central_pool_qty(stand_id, pool)

        transfer = StandTransfer(
            manager_id=actor.id,
            from_client_id=None,
            to_client_id=None,
            stand_id=stand_id,
            quantity=total,
            operation=StandTransferOperation.CENTRAL_SET.value,
            to_was_new=False,
            note=(note or "").strip() or None,
        )
        self._session.add(transfer)
        await self._session.flush()
        return StandAllocateResult(transfer_id=transfer.id)

    async def allocate_central_to_manager(
        self,
        *,
        actor: WebUser,
        manager_id: int,
        stand_id: int,
        quantity: int,
        note: str | None = None,
    ) -> StandAllocateResult:
        self._assert_actor_may_allocate(actor)
        await self._assert_field_manager_id(manager_id)

        stand = await self._stands.get_by_id(stand_id)
        if stand is None or not stand.is_active:
            raise ValueError("Стенд не знайдено")

        qty = max(1, int(quantity))
        await self._remove_central_pool_qty(stand_id, qty)
        await self._add_central_allocation(manager_id, stand_id, qty)

        transfer = StandTransfer(
            manager_id=manager_id,
            from_client_id=None,
            to_client_id=None,
            stand_id=stand_id,
            quantity=qty,
            operation=StandTransferOperation.ALLOCATE_CENTRAL.value,
            to_was_new=False,
            note=(note or "").strip() or None,
        )
        self._session.add(transfer)
        await self._session.flush()
        return StandAllocateResult(transfer_id=transfer.id)

    async def transfer_central_to_regional(
        self,
        *,
        actor: WebUser,
        manager_id: int,
        stand_id: int,
        quantity: int,
        note: str | None = None,
    ) -> StandAllocateResult:
        self._assert_actor_may_allocate(actor)
        await self._assert_field_manager_id(manager_id)

        stand = await self._stands.get_by_id(stand_id)
        if stand is None or not stand.is_active:
            raise ValueError("Стенд не знайдено")

        qty = max(1, int(quantity))
        await self._remove_central_allocation(manager_id, stand_id, qty)
        await self._add_warehouse_qty(manager_id, stand_id, qty)

        transfer = StandTransfer(
            manager_id=manager_id,
            from_client_id=None,
            to_client_id=None,
            stand_id=stand_id,
            quantity=qty,
            operation=StandTransferOperation.CENTRAL_TO_REGIONAL.value,
            to_was_new=False,
            note=(note or "").strip() or None,
        )
        self._session.add(transfer)
        await self._session.flush()
        return StandAllocateResult(transfer_id=transfer.id)

    async def _add_client_stand_qty(
        self,
        client_id: int,
        stand_id: int,
        qty: int,
    ) -> None:
        client = await self._clients.get_by_id(client_id)
        if client is None:
            raise ValueError("Торгову точку не знайдено")
        for link in client.stand_links:
            if link.stand_id == stand_id:
                link.quantity = max(1, int(getattr(link, "quantity", 1) or 1)) + qty
                await self._session.flush()
                return
        self._session.add(
            ClientStand(client_id=client_id, stand_id=stand_id, quantity=qty)
        )
        await self._session.flush()

    async def list_warehouse_stock(self, manager_id: int) -> list[WarehouseStockRow]:
        result = await self._session.execute(
            select(ManagerStandStock)
            .where(
                ManagerStandStock.manager_id == manager_id,
                ManagerStandStock.quantity > 0,
            )
            .options(selectinload(ManagerStandStock.stand))
            .order_by(ManagerStandStock.stand_id)
        )
        rows: list[WarehouseStockRow] = []
        for item in result.scalars().all():
            if item.stand is None or not item.stand.is_active:
                continue
            rows.append(
                WarehouseStockRow(
                    stand_id=item.stand_id,
                    stand_name=item.stand.name,
                    quantity=int(item.quantity),
                )
            )
        return rows

    async def _remove_stand_qty(
        self,
        client_id: int,
        stand_id: int,
        qty: int,
    ) -> None:
        client = await self._clients.get_by_id(client_id)
        if client is None:
            raise ValueError("Торгову точку не знайдено")
        available = self._stand_qty_on_client(client, stand_id)
        if available < qty:
            raise ValueError(
                f"Недостатньо стендів на ТТ (є {available}, потрібно {qty})"
            )
        for link in list(client.stand_links):
            if link.stand_id != stand_id:
                continue
            current = max(1, int(getattr(link, "quantity", 1) or 1))
            if qty >= current:
                await self._session.delete(link)
            else:
                link.quantity = current - qty
            await self._session.flush()
            return
        raise ValueError("У торгової точки немає цього стенду")

    async def move_stand(
        self,
        *,
        actor: WebUser,
        from_client_id: int,
        stand_id: int,
        quantity: int,
        to_kind: str,
        to_client_id: int | None,
        new_name: str | None,
        new_address: str | None,
        new_city: str | None,
        new_oblast: str | None,
    ) -> StandMoveResult:
        from_client = await self._clients.get_by_id(from_client_id)
        if from_client is None:
            raise ValueError("Відправника не знайдено")
        effective_manager_id = self._assert_actor_may_edit_client(actor, from_client)

        stand = await self._stands.get_by_id(stand_id)
        if stand is None or not stand.is_active:
            raise ValueError("Стенд не знайдено")

        qty = max(1, int(quantity))
        if qty != 1:
            raise ValueError("За одну операцію можна перемістити 1 стенд")

        if not await self.client_has_stand(from_client_id, stand_id):
            raise ValueError("У відправника немає цього стенду")
        to_was_new = False

        if to_kind == "new":
            name = (new_name or "").strip()
            if not name:
                raise ValueError("Вкажіть назву нової ТТ")
            address = (new_address or "").strip() or "—"
            oblast_name = (new_oblast or "").strip()
            city = (new_city or "").strip()
            comment_parts = []
            if city:
                comment_parts.append(f"місто:{city}")
            comment = "\n".join(comment_parts) if comment_parts else None

            region_id = await self._resolve_region_id(
                effective_manager_id,
                oblast_name or (from_client.region.name if from_client.region else "—"),
            )
            to_client = await self._clients.create(
                manager_id=effective_manager_id,
                region_id=region_id,
                name=name,
                address=address,
                comment=comment,
                stand_ids=[],
            )
            to_was_new = True
        else:
            if to_client_id is None:
                raise ValueError("Оберіть отримувача")
            to_client = await self._clients.get_by_id(to_client_id)
            if to_client is None:
                raise ValueError("Отримувача не знайдено")
            if to_client.manager_id != effective_manager_id:
                raise ValueError("Отримувач має бути у того ж менеджера")

        if from_client.id == to_client.id:
            raise ValueError("Відправник і отримувач не повинні збігатися")

        if await self.client_has_stand(to_client.id, stand_id):
            raise ValueError("У отримувача вже є цей стенд")

        await self._remove_stand_qty(from_client_id, stand_id, qty)

        self._session.add(
            ClientStand(client_id=to_client.id, stand_id=stand_id, quantity=qty)
        )

        transfer = StandTransfer(
            manager_id=effective_manager_id,
            from_client_id=from_client_id,
            to_client_id=to_client.id,
            stand_id=stand_id,
            quantity=qty,
            operation=StandTransferOperation.MOVE.value,
            to_was_new=to_was_new,
        )
        self._session.add(transfer)
        await self._session.flush()

        return StandMoveResult(
            transfer_id=transfer.id,
            to_client_id=to_client.id,
            to_client_name=to_client.name,
        )

    async def write_off_stand(
        self,
        *,
        actor: WebUser,
        from_client_id: int,
        stand_id: int,
        quantity: int,
        note: str | None = None,
    ) -> StandWriteOffResult:
        from_client = await self._clients.get_by_id(from_client_id)
        if from_client is None:
            raise ValueError("Торгову точку не знайдено")
        effective_manager_id = self._assert_actor_may_edit_client(actor, from_client)

        stand = await self._stands.get_by_id(stand_id)
        if stand is None or not stand.is_active:
            raise ValueError("Стенд не знайдено")

        qty = max(1, int(quantity))
        if not await self.client_has_stand(from_client_id, stand_id):
            raise ValueError("У торгової точки немає цього стенду")

        await self._remove_stand_qty(from_client_id, stand_id, qty)

        note_clean = (note or "").strip() or None
        transfer = StandTransfer(
            manager_id=effective_manager_id,
            from_client_id=from_client_id,
            to_client_id=None,
            stand_id=stand_id,
            quantity=qty,
            operation=StandTransferOperation.WRITE_OFF.value,
            to_was_new=False,
            note=note_clean,
        )
        self._session.add(transfer)
        await self._session.flush()

        return StandWriteOffResult(transfer_id=transfer.id)

    async def allocate_stand_stock(
        self,
        *,
        actor: WebUser,
        manager_id: int,
        stand_id: int,
        quantity: int,
        note: str | None = None,
    ) -> StandAllocateResult:
        """Зворотна сумісність: виділення на центральний склад менеджера."""
        return await self.allocate_central_to_manager(
            actor=actor,
            manager_id=manager_id,
            stand_id=stand_id,
            quantity=quantity,
            note=note,
        )

    async def move_to_warehouse(
        self,
        *,
        actor: WebUser,
        from_client_id: int,
        stand_id: int,
        quantity: int,
        note: str | None = None,
    ) -> StandWarehouseResult:
        from_client = await self._clients.get_by_id(from_client_id)
        if from_client is None:
            raise ValueError("Торгову точку не знайдено")
        effective_manager_id = self._assert_actor_may_edit_client(actor, from_client)
        self._assert_actor_may_operate_for_manager(actor, effective_manager_id)

        stand = await self._stands.get_by_id(stand_id)
        if stand is None or not stand.is_active:
            raise ValueError("Стенд не знайдено")

        qty = max(1, int(quantity))
        if not await self.client_has_stand(from_client_id, stand_id):
            raise ValueError("У торгової точки немає цього стенду")

        await self._remove_stand_qty(from_client_id, stand_id, qty)
        await self._add_warehouse_qty(effective_manager_id, stand_id, qty)

        transfer = StandTransfer(
            manager_id=effective_manager_id,
            from_client_id=from_client_id,
            to_client_id=None,
            stand_id=stand_id,
            quantity=qty,
            operation=StandTransferOperation.TO_WAREHOUSE.value,
            to_was_new=False,
            note=(note or "").strip() or None,
        )
        self._session.add(transfer)
        await self._session.flush()
        return StandWarehouseResult(transfer_id=transfer.id)

    async def move_from_warehouse(
        self,
        *,
        actor: WebUser,
        manager_id: int,
        stand_id: int,
        quantity: int,
        to_kind: str,
        to_client_id: int | None,
        new_name: str | None,
        new_address: str | None,
        new_city: str | None,
        new_oblast: str | None,
    ) -> StandMoveResult:
        self._assert_actor_may_operate_for_manager(actor, manager_id)
        await self._assert_field_manager_id(manager_id)

        stand = await self._stands.get_by_id(stand_id)
        if stand is None or not stand.is_active:
            raise ValueError("Стенд не знайдено")

        qty = max(1, int(quantity))
        if qty != 1:
            raise ValueError("За одну операцію можна встановити 1 стенд")

        available = await self._warehouse_qty(manager_id, stand_id)
        if available < qty:
            raise ValueError(
                f"Недостатньо стендів на складі (є {available}, потрібно {qty})"
            )

        to_was_new = False
        if to_kind == "new":
            name = (new_name or "").strip()
            if not name:
                raise ValueError("Вкажіть назву нової ТТ")
            address = (new_address or "").strip() or "—"
            oblast_name = (new_oblast or "").strip()
            city = (new_city or "").strip()
            comment_parts = []
            if city:
                comment_parts.append(f"місто:{city}")
            comment = "\n".join(comment_parts) if comment_parts else None
            regions = await self._regions.list_by_manager(manager_id)
            default_oblast = regions[0].name if regions else "—"
            region_id = await self._resolve_region_id(
                manager_id,
                oblast_name or default_oblast,
            )
            to_client = await self._clients.create(
                manager_id=manager_id,
                region_id=region_id,
                name=name,
                address=address,
                comment=comment,
                stand_ids=[],
            )
            to_was_new = True
        else:
            if to_client_id is None:
                raise ValueError("Оберіть торгову точку")
            to_client = await self._clients.get_by_id(to_client_id)
            if to_client is None:
                raise ValueError("Торгову точку не знайдено")
            if to_client.manager_id != manager_id:
                raise ValueError("Торгова точка має належати цьому менеджеру")

        if await self.client_has_stand(to_client.id, stand_id):
            raise ValueError("У торгової точки вже є цей стенд")

        await self._remove_warehouse_qty(manager_id, stand_id, qty)
        await self._add_client_stand_qty(to_client.id, stand_id, qty)

        transfer = StandTransfer(
            manager_id=manager_id,
            from_client_id=None,
            to_client_id=to_client.id,
            stand_id=stand_id,
            quantity=qty,
            operation=StandTransferOperation.FROM_WAREHOUSE.value,
            to_was_new=to_was_new,
        )
        self._session.add(transfer)
        await self._session.flush()

        return StandMoveResult(
            transfer_id=transfer.id,
            to_client_id=to_client.id,
            to_client_name=to_client.name,
        )

    @staticmethod
    def _history_endpoint_labels(transfer: StandTransfer) -> tuple[str, str]:
        op = transfer.operation
        if op == StandTransferOperation.ALLOCATE.value:
            return ALLOCATE_SOURCE_LABEL, WAREHOUSE_LOCATION_LABEL
        if op == StandTransferOperation.CENTRAL_SET.value:
            return "—", CENTRAL_WAREHOUSE_LABEL
        if op == StandTransferOperation.ALLOCATE_CENTRAL.value:
            return CENTRAL_WAREHOUSE_LABEL, MANAGER_CENTRAL_LABEL
        if op == StandTransferOperation.CENTRAL_TO_REGIONAL.value:
            return MANAGER_CENTRAL_LABEL, WAREHOUSE_LOCATION_LABEL
        if op == StandTransferOperation.TO_WAREHOUSE.value:
            from_name = transfer.from_client.name if transfer.from_client else "—"
            return from_name, WAREHOUSE_LOCATION_LABEL
        if op == StandTransferOperation.FROM_WAREHOUSE.value:
            to_name = transfer.to_client.name if transfer.to_client else "—"
            return WAREHOUSE_LOCATION_LABEL, to_name
        if op == StandTransferOperation.WRITE_OFF.value:
            from_name = transfer.from_client.name if transfer.from_client else "—"
            return from_name, "—"
        from_name = transfer.from_client.name if transfer.from_client else "—"
        to_name = transfer.to_client.name if transfer.to_client else "—"
        return from_name, to_name

    async def _resolve_region_id(self, manager_id: int, oblast_name: str) -> int:
        name = oblast_name.strip() or "—"
        regions = await self._regions.list_by_manager(manager_id)
        for r in regions:
            if r.name.strip().casefold() == name.casefold():
                return r.id
        created = await self._regions.create(manager_id, name)
        return created.id

    async def list_history(
        self,
        *,
        viewer: WebUser,
        year: int | None,
        month: int | None,
        manager_id: int | None,
        region_id: int | None,
        city: str | None,
        stand_id: int | None,
    ) -> list[StandTransferRow]:
        stmt = (
            select(StandTransfer)
            .options(
                selectinload(StandTransfer.manager),
                selectinload(StandTransfer.from_client).selectinload(Client.region),
                selectinload(StandTransfer.to_client).selectinload(Client.region),
                selectinload(StandTransfer.stand),
            )
            .order_by(StandTransfer.created_at.desc())
        )
        if viewer.role not in ORG_VIEW_ROLES:
            owner = data_owner_manager_id(viewer) or viewer.id
            stmt = stmt.where(StandTransfer.manager_id == owner)
        elif manager_id is not None:
            stmt = stmt.where(StandTransfer.manager_id == manager_id)

        if year is not None:
            stmt = stmt.where(extract("year", StandTransfer.created_at) == year)
        if month is not None:
            stmt = stmt.where(extract("month", StandTransfer.created_at) == month)
        if stand_id is not None:
            stmt = stmt.where(StandTransfer.stand_id == stand_id)

        result = await self._session.execute(stmt)
        transfers = list(result.scalars().all())

        rows: list[StandTransferRow] = []
        for t in transfers:
            fc = t.from_client
            tc = t.to_client
            if region_id is not None or city:
                if t.operation in (
                    StandTransferOperation.ALLOCATE.value,
                    StandTransferOperation.CENTRAL_SET.value,
                    StandTransferOperation.ALLOCATE_CENTRAL.value,
                    StandTransferOperation.CENTRAL_TO_REGIONAL.value,
                ):
                    continue
                from_match = fc is not None and (
                    (region_id is None or fc.region_id == region_id)
                    and (not city or client_city(fc) == city)
                )
                to_match = tc is not None and (
                    (region_id is None or tc.region_id == region_id)
                    and (not city or client_city(tc) == city)
                )
                if not from_match and not to_match:
                    continue
            from_label, to_label = self._history_endpoint_labels(t)
            rows.append(
                StandTransferRow(
                    transfer=t,
                    from_label=from_label,
                    to_label=to_label,
                    from_city=client_city(fc) if fc is not None else "",
                    to_city=client_city(tc) if tc is not None else "",
                    from_oblast=client_oblast(fc) if fc is not None else "",
                    to_oblast=client_oblast(tc) if tc is not None else "",
                )
            )
        return rows
