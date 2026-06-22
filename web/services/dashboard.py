from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from config.team import filter_regional_managers
from database.models import Brand, Client, Sale, Stand, User, Visit
from database.repositories.brand import BrandRepository
from database.repositories.client import ClientRepository
from database.repositories.sale import SaleRepository
from database.repositories.stand import StandRepository
from database.repositories.user import UserRepository
from database.repositories.visit import VisitRepository
from web.analytics_periods import DateRange


@dataclass
class VisitStats:
    total: int
    today: int
    week: int


@dataclass
class ManagerVisitCount:
    manager: User
    count: int


@dataclass(frozen=True)
class ClientGalleryPhoto:
    visit_id: int
    photo_url: str
    visit_at: datetime


@dataclass(frozen=True)
class ClientSalesBrandRow:
    brand_name: str
    quantity: Decimal


class DashboardService:
    CLIENTS_PER_PAGE = 50
    RESERVES_PER_PAGE = 50

    def __init__(self, session: AsyncSession) -> None:
        self._visits = VisitRepository(session)
        self._clients = ClientRepository(session)
        self._users = UserRepository(session)
        self._stands = StandRepository(session)
        self._brands = BrandRepository(session)
        self._sales = SaleRepository(session)

    async def list_managers(self) -> list[User]:
        """Регіональні менеджери (поле) — без керівників (leader) та sales_manager."""
        users = await self._users.list_all()
        return filter_regional_managers(users)

    async def list_visits(
        self,
        *,
        manager_id: int | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> tuple[list[Visit], int, int, int]:
        total = await self._visits.count(manager_id=manager_id)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page
        visits = await self._visits.list_recent(
            manager_id=manager_id,
            limit=per_page,
            offset=offset,
        )
        return visits, total, page, total_pages

    async def get_visit(self, visit_id: int) -> Visit | None:
        return await self._visits.get_by_id(visit_id)

    async def list_clients(self) -> list[Client]:
        return await self._clients.list_all()

    async def list_clients_for_filters(
        self,
        *,
        manager_id: int | None = None,
    ) -> list[Client]:
        return await self._clients.list_for_filter_options(manager_id=manager_id)

    async def list_clients_page(
        self,
        filters,
        *,
        page: int = 1,
        per_page: int | None = None,
    ) -> tuple[list[Client], int, int, int]:
        per_page = per_page or self.CLIENTS_PER_PAGE
        total = await self._clients.count_filtered(
            manager_id=filters.manager_id,
            region_id=filters.region_id,
            city=filters.city or None,
            stand_id=filters.stand_id,
        )
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page
        clients = await self._clients.list_filtered(
            manager_id=filters.manager_id,
            region_id=filters.region_id,
            city=filters.city or None,
            stand_id=filters.stand_id,
            limit=per_page,
            offset=offset,
        )
        return clients, total, page, total_pages

    async def list_active_stands(self) -> list[Stand]:
        return await self._stands.list_active()

    async def list_active_brands(self) -> list[Brand]:
        return await self._brands.list_active()

    async def get_client(self, client_id: int) -> Client | None:
        return await self._clients.get_by_id_with_manager(client_id)

    async def list_client_visits(self, client_id: int) -> list[Visit]:
        return await self._visits.list_by_client(client_id)

    async def client_visit_count(self, client_id: int) -> int:
        return await self._visits.count_by_client(client_id)

    async def client_visit_gallery(self, client_id: int) -> list[ClientGalleryPhoto]:
        visits = await self._visits.list_by_client(client_id)
        items: list[ClientGalleryPhoto] = []
        for visit in visits:
            for photo in visit.photos:
                items.append(
                    ClientGalleryPhoto(
                        visit_id=visit.id,
                        photo_url=photo.photo_url,
                        visit_at=visit.created_at,
                    )
                )
        return items

    async def client_sales_in_period(
        self,
        client_id: int,
        period: DateRange,
        *,
        brand_id: int | None = None,
    ) -> tuple[list[Sale], Decimal]:
        sales = await self._sales.list_for_client_between(
            client_id,
            period.start,
            period.end,
            brand_id=brand_id,
        )
        total = sum((s.quantity for s in sales if s.quantity), Decimal(0))
        return sales, total

    async def client_sales_by_brand(
        self,
        client_id: int,
        period: DateRange,
        *,
        brand_id: int | None = None,
    ) -> list[ClientSalesBrandRow]:
        sales, _ = await self.client_sales_in_period(
            client_id, period, brand_id=brand_id
        )
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for sale in sales:
            if sale.brand:
                totals[sale.brand.name] += sale.quantity
        return [
            ClientSalesBrandRow(brand_name=name, quantity=qty)
            for name, qty in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    async def visit_stats(self, *, manager_id: int | None = None) -> VisitStats:
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = start_of_day - timedelta(days=start_of_day.weekday())
        total, today, week = await self._visits.stats_summary(
            start_of_day=start_of_day,
            start_of_week=start_of_week,
            manager_id=manager_id,
        )
        return VisitStats(total=total, today=today, week=week)

    async def visits_per_manager(self) -> list[ManagerVisitCount]:
        managers = await self._users.list_all()
        result: list[ManagerVisitCount] = []
        for manager in managers:
            if manager.role != "manager":
                continue
            count = await self._visits.count(manager_id=manager.id)
            result.append(ManagerVisitCount(manager=manager, count=count))
        result.sort(key=lambda item: item.count, reverse=True)
        return result
