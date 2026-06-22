from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Client, ClientStand, Sale, Stand, User, UserRole
from database.repositories.sale import SaleRepository
from database.repositories.user import UserRepository
from web.analytics_periods import DateRange, rolling_months_range
from web.client_geo import client_city, client_oblast
from web.services.clients_filter import (
    ClientFilters,
    SalesFilters,
    client_matches_filters,
    filter_clients,
    sales_filters_to_client,
)

from config.team import filter_regional_managers


@dataclass
class AggRow:
    label: str
    value: Decimal
    extra: str = ""


@dataclass
class StandReportRow:
    """Рядок звіту по стендах (як SK_Account: менеджер/місто/область × марка)."""

    count: int
    manager: str | None = None
    stand: str | None = None
    city: str | None = None
    oblast: str | None = None


@dataclass
class CompareRow:
    label: str
    current: Decimal
    previous: Decimal

    @property
    def delta(self) -> Decimal:
        return self.current - self.previous

    @property
    def pct(self) -> float | None:
        if self.previous == 0:
            return None
        return float(self.delta / self.previous * 100)


@dataclass
class SplitRow:
    left: str
    middle: str
    value: Decimal


@dataclass
class MatrixColumn:
    key: str
    label: str
    total_points: int
    worked_points: int

    @property
    def pct(self) -> int:
        if self.total_points <= 0:
            return 0
        return int(round(self.worked_points / self.total_points * 100))


@dataclass
class MatrixCell:
    """Клітинка матриці продажів: продаж / стенд без продажу / стенду немає."""

    kind: Literal["sale", "no_sale", "na"]
    quantity: Decimal | None = None


@dataclass(frozen=True)
class InactiveStandRow:
    period_label: str
    stand_name: str
    client_label: str
    client_id: int
    manager_name: str
    region_name: str
    city: str
    oblast: str
    placement_count: int


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sales = SaleRepository(session)
        self._users = UserRepository(session)
        self._sales_cache: dict[tuple, list[Sale]] = {}
        self._clients_with_stands: list[Client] | None = None
        self._stand_names: dict[int, str] | None = None
        self._stand_col_match_cache: dict[tuple[str, str], list[str]] = {}

    @staticmethod
    def _sales_cache_key(
        date_range: DateRange,
        filters: SalesFilters | None,
    ) -> tuple:
        filter_key = ()
        if filters is not None:
            filter_key = (
                filters.manager_id,
                filters.region_id,
                filters.city,
                filters.stand_id,
                filters.brand_id,
            )
        return (date_range.start, date_range.end, filter_key)

    async def _cached_stand_names(self) -> dict[int, str]:
        if self._stand_names is None:
            self._stand_names = await self._stand_names_by_id()
        return self._stand_names

    async def list_managers(self) -> list[User]:
        users = await self._users.list_all()
        return filter_regional_managers(users)

    async def _stand_names_by_id(self) -> dict[int, str]:
        result = await self._session.execute(select(Stand))
        return {s.id: s.name for s in result.scalars().all()}

    @staticmethod
    def _needs_sale_post_filter(filters: SalesFilters) -> bool:
        return any(
            [
                filters.region_id is not None,
                filters.city,
                filters.stand_id is not None,
                filters.brand_id is not None,
            ]
        )

    def _sale_matches(
        self,
        sale: Sale,
        filters: SalesFilters,
        stand_names: dict[int, str],
    ) -> bool:
        if filters.brand_id is not None and sale.brand_id != filters.brand_id:
            return False
        client = sale.client
        if client is None:
            return False
        client_filter = ClientFilters(
            manager_id=filters.manager_id,
            region_id=filters.region_id,
            city=filters.city,
            stand_id=None,
        )
        if not client_matches_filters(client, client_filter):
            return False
        if filters.stand_id is not None:
            stand_ids = {
                link.stand_id for link in client.stand_links if link.stand_id is not None
            }
            if filters.stand_id not in stand_ids:
                return False
            stand_name = stand_names.get(filters.stand_id, "")
            brand_name = sale.brand.name if sale.brand else ""
            if stand_name and not self._stand_key_matches_matrix_col(stand_name, brand_name):
                return False
        return True

    async def _sales_in_range(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[Sale]:
        cache_key = self._sales_cache_key(date_range, filters)
        if cache_key in self._sales_cache:
            return self._sales_cache[cache_key]

        manager_id = filters.manager_id if filters else None
        sales = await self._sales.list_between(
            date_range.start,
            date_range.end,
            manager_id=manager_id,
        )
        if filters is not None and self._needs_sale_post_filter(filters):
            stand_names = (
                await self._cached_stand_names()
                if filters.stand_id is not None
                else {}
            )
            sales = [s for s in sales if self._sale_matches(s, filters, stand_names)]

        self._sales_cache[cache_key] = sales
        return sales

    async def sales_total(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> Decimal:
        if filters is None or not self._needs_sale_post_filter(filters):
            return await self._sales.sum_quantity_between(
                date_range.start,
                date_range.end,
                manager_id=filters.manager_id if filters else None,
            )
        sales = await self._sales_in_range(date_range, filters)
        return sum((s.quantity for s in sales if s.quantity), Decimal(0))

    async def sales_ledger(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
        *,
        limit: int = 500,
    ) -> list[Sale]:
        sales = await self._sales_in_range(date_range, filters)
        sales.sort(key=lambda s: (s.created_at, s.id), reverse=True)
        return sales[:limit]

    async def sales_by_manager(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[AggRow]:
        sales = await self._sales_in_range(date_range, filters)
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for s in sales:
            totals[s.manager.name] += s.quantity
        return [
            AggRow(label=k, value=v)
            for k, v in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    async def sales_by_brand(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[AggRow]:
        sales = await self._sales_in_range(date_range, filters)
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for s in sales:
            totals[s.brand.name] += s.quantity
        return [
            AggRow(label=k, value=v)
            for k, v in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    async def sales_by_client(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[AggRow]:
        sales = await self._sales_in_range(date_range, filters)
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for s in sales:
            totals[s.client.name] += s.quantity
        return [
            AggRow(label=k, value=v)
            for k, v in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    async def sales_by_oblast(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[AggRow]:
        sales = await self._sales_in_range(date_range, filters)
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for s in sales:
            totals[client_oblast(s.client)] += s.quantity
        return [
            AggRow(label=k, value=v)
            for k, v in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    async def brands_by_city(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[AggRow]:
        sales = await self._sales_in_range(date_range, filters)
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for s in sales:
            key = f"{client_city(s.client)} · {s.brand.name}"
            totals[key] += s.quantity
        return [
            AggRow(label=k, value=v)
            for k, v in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    async def brands_by_city_split(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[SplitRow]:
        sales = await self._sales_in_range(date_range, filters)
        totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        for s in sales:
            totals[(client_city(s.client), s.brand.name)] += s.quantity
        return [
            SplitRow(left=city, middle=brand, value=value)
            for (city, brand), value in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    async def brands_by_oblast(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[AggRow]:
        sales = await self._sales_in_range(date_range, filters)
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for s in sales:
            key = f"{client_oblast(s.client)} · {s.brand.name}"
            totals[key] += s.quantity
        return [
            AggRow(label=k, value=v)
            for k, v in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    async def brands_by_oblast_split(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[SplitRow]:
        sales = await self._sales_in_range(date_range, filters)
        totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        for s in sales:
            totals[(client_oblast(s.client), s.brand.name)] += s.quantity
        return [
            SplitRow(left=oblast, middle=brand, value=value)
            for (oblast, brand), value in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    async def sales_matrix(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
        *,
        top_brands: int = 12,
    ) -> tuple[list[str], list[dict[str, object]]]:
        sales = await self._sales_in_range(date_range, filters)

        # Brand totals to pick top N columns
        brand_totals: dict[str, Decimal] = defaultdict(Decimal)
        client_totals: dict[str, Decimal] = defaultdict(Decimal)
        cell: dict[tuple[str, str], Decimal] = defaultdict(Decimal)

        for s in sales:
            brand = s.brand.name
            client = s.client.name
            brand_totals[brand] += s.quantity
            client_totals[client] += s.quantity
            cell[(client, brand)] += s.quantity

        brands_sorted = [b for b, _ in sorted(brand_totals.items(), key=lambda x: x[1], reverse=True)]
        brands_main = brands_sorted[:top_brands]
        has_other = len(brands_sorted) > top_brands
        if has_other:
            brands = brands_main + ["Інше"]
        else:
            brands = brands_main

        clients_sorted = [c for c, _ in sorted(client_totals.items(), key=lambda x: x[1], reverse=True)]
        rows: list[dict[str, object]] = []
        for client in clients_sorted:
            row: dict[str, object] = {"client": client, "total": client_totals[client]}
            other_sum = Decimal(0)
            for brand in brands_main:
                q = cell.get((client, brand), Decimal(0))
                row[brand] = q
            if has_other:
                for brand in brands_sorted[top_brands:]:
                    other_sum += cell.get((client, brand), Decimal(0))
                row["Інше"] = other_sum
            rows.append(row)

        return brands, rows

    async def sales_matrix_from_stands(
        self,
        date_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> tuple[list[MatrixColumn], list[dict[str, object]]]:
        """
        Matrix like SK_Account:
        - columns are stands (placements) from client_stands for the selected manager (or all)
        - header meta shows: total points / worked points / %
        - cell value is sold quantity for brands matching the stand column
        """
        clients = await self._all_clients_with_stands()
        client_filters = sales_filters_to_client(filters)
        if client_filters is not None:
            clients = filter_clients(clients, client_filters)

        sales = await self._sales_in_range(date_range, filters)

        # sales by client & normalized matrix column key
        sales_by_client_col: dict[tuple[int, str], Decimal] = defaultdict(Decimal)
        col_keys_set: set[str] = set()
        for s in sales:
            if s.quantity is None or s.quantity <= 0:
                continue
            col = self._sales_matrix_col_key_from_brand(s.brand.name)
            sales_by_client_col[(s.client_id, col)] += s.quantity
            col_keys_set.add(col)

        # placements (стенди з карток клієнтів)
        placements: list[tuple[int, str]] = []
        for c in clients:
            for link in c.stand_links:
                stand: Stand | None = link.stand
                if stand is None or not stand.is_active:
                    continue
                placements.append((c.id, stand.name))
                col_keys_set.add(self._sales_matrix_col_key_from_brand(stand.name))

        col_keys_all = sorted(col_keys_set, key=lambda x: x.lower())

        # Стовпці матриці: усі марки з продажами за період (+ стенди з карток для «0»/«·»)
        col_keys_visible = sorted(
            {col for (_, col), qty in sales_by_client_col.items() if qty > 0},
            key=lambda x: x.lower(),
        )

        total_points: dict[str, int] = defaultdict(int)
        worked_points: dict[str, int] = defaultdict(int)
        for client_id, stand_name in placements:
            matching_cols = self._matching_matrix_cols_cached(stand_name, col_keys_all)
            for col in matching_cols:
                total_points[col] += 1
                if sales_by_client_col.get((client_id, col), Decimal(0)) > 0:
                    worked_points[col] += 1

        # Продаж без стенду в картці теж зараховуємо в «спрацювало» (як у клітинках матриці)
        for col in col_keys_visible:
            sold_tt = {
                cid
                for (cid, c), qty in sales_by_client_col.items()
                if c == col and qty > 0
            }
            if len(sold_tt) > worked_points[col]:
                worked_points[col] = len(sold_tt)
            if total_points[col] < worked_points[col]:
                total_points[col] = worked_points[col]

        columns: list[MatrixColumn] = [
            MatrixColumn(
                key=col,
                label=col,
                total_points=total_points.get(col, 0),
                worked_points=worked_points.get(col, 0),
            )
            for col in col_keys_visible
        ]

        clients_by_id = {c.id: c for c in clients}
        base_names = {c.id: c.name for c in clients}
        name_counts = Counter(base_names.values())

        def matrix_client_label(cid: int) -> str:
            c = clients_by_id.get(cid)
            name = base_names.get(cid, f"#{cid}")
            if name_counts[name] <= 1:
                return name
            if c and c.region and c.region.name:
                return f"{name} · {c.region.name}"
            return f"{name} (#{cid})"

        col_keys_visible_set = set(col_keys_visible)

        # Лише ТТ, де за період був хоча б один продаж
        clients_with_sales: set[int] = {
            cid
            for (cid, col), qty in sales_by_client_col.items()
            if qty > 0 and col in col_keys_visible_set
        }

        ordered_clients = sorted(
            clients_with_sales,
            key=lambda cid: (
                -sum(
                    sales_by_client_col.get((cid, col), Decimal(0))
                    for col in col_keys_visible
                ),
                matrix_client_label(cid).lower(),
            ),
        )

        rows: list[dict[str, object]] = []
        for cid in ordered_clients:
            client = clients_by_id.get(cid)
            cells: dict[str, MatrixCell] = {}
            total = Decimal(0)
            for col in col_keys_visible:
                qty = sales_by_client_col.get((cid, col), Decimal(0))
                if qty > 0:
                    cells[col] = MatrixCell(kind="sale", quantity=qty)
                    total += qty
                elif client is not None and self._client_has_stand_for_col(client, col):
                    cells[col] = MatrixCell(kind="no_sale")
                else:
                    cells[col] = MatrixCell(kind="na")
            if total <= 0:
                continue
            rows.append(
                {
                    "client_id": cid,
                    "client": matrix_client_label(cid),
                    "cells": cells,
                    "total": total,
                }
            )

        return columns, rows

    @staticmethod
    def _compare_sorted(
        report_map: dict[str, Decimal],
        base_map: dict[str, Decimal],
    ) -> list[CompareRow]:
        labels = set(report_map) | set(base_map)
        rows = [
            CompareRow(
                label=label,
                current=report_map.get(label, Decimal(0)),
                previous=base_map.get(label, Decimal(0)),
            )
            for label in labels
        ]
        return sorted(rows, key=lambda r: (r.current, r.label.lower()), reverse=True)

    async def compare_managers_table(
        self,
        report_range: DateRange,
        base_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[CompareRow]:
        managers = await self.list_managers()
        if filters and filters.manager_id is not None:
            managers = [m for m in managers if m.id == filters.manager_id]

        if filters is None or not self._needs_sale_post_filter(filters):
            report_totals = await self._sales.sum_quantity_by_manager_between(
                report_range.start,
                report_range.end,
            )
            base_totals = await self._sales.sum_quantity_by_manager_between(
                base_range.start,
                base_range.end,
            )
            rows: list[CompareRow] = []
            total_report = Decimal(0)
            total_base = Decimal(0)
            for manager in managers:
                report_total = report_totals.get(manager.id, Decimal(0))
                base_total = base_totals.get(manager.id, Decimal(0))
                rows.append(
                    CompareRow(
                        label=manager.name,
                        current=report_total,
                        previous=base_total,
                    )
                )
                total_report += report_total
                total_base += base_total
            rows.append(
                CompareRow(label="Разом", current=total_report, previous=total_base)
            )
            return rows

        rows = []
        total_report = Decimal(0)
        total_base = Decimal(0)
        for manager in managers:
            mgr_filter = SalesFilters(
                manager_id=manager.id,
                region_id=filters.region_id if filters else None,
                city=filters.city if filters else None,
                stand_id=filters.stand_id if filters else None,
                brand_id=filters.brand_id if filters else None,
            )
            report_total = await self.sales_total(report_range, mgr_filter)
            base_total = await self.sales_total(base_range, mgr_filter)
            rows.append(
                CompareRow(
                    label=manager.name,
                    current=report_total,
                    previous=base_total,
                )
            )
            total_report += report_total
            total_base += base_total

        rows.append(
            CompareRow(label="Разом", current=total_report, previous=total_base)
        )
        return rows

    @staticmethod
    def _count_worked_stands_from_sales(sales: list[Sale]) -> int:
        """
        Унікальні пари (торгова точка, колонка стенду) з продажами за період.
        ADO в 3 різних ТТ → 3; одна ТТ з ADO і BIG → 2.
        Кожна ТТ з продажем дає щонайменше один такий стенд.
        """
        pairs: set[tuple[int, str]] = set()
        for s in sales:
            if s.quantity is None or s.quantity <= 0:
                continue
            col = AnalyticsService._sales_matrix_col_key_from_brand(s.brand.name)
            pairs.add((s.client_id, col))
        return len(pairs)

    async def compare_kpis(
        self,
        report_range: DateRange,
        base_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[CompareRow]:
        report_sales = await self._sales_in_range(report_range, filters)
        base_sales = await self._sales_in_range(base_range, filters)

        report_shops = len({s.client_id for s in report_sales if s.quantity and s.quantity > 0})
        base_shops = len({s.client_id for s in base_sales if s.quantity and s.quantity > 0})
        report_stands = self._count_worked_stands_from_sales(report_sales)
        base_stands = self._count_worked_stands_from_sales(base_sales)

        return [
            CompareRow(
                label="Кількість торгових точок, що спрацювали",
                current=Decimal(report_shops),
                previous=Decimal(base_shops),
            ),
            CompareRow(
                label="Кількість стендів, що спрацювали",
                current=Decimal(report_stands),
                previous=Decimal(base_stands),
            ),
        ]

    async def compare_brands(
        self,
        report_range: DateRange,
        base_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[CompareRow]:
        report_sales = await self._sales_in_range(report_range, filters)
        base_sales = await self._sales_in_range(base_range, filters)

        def by_brand(rows: list[Sale]) -> dict[str, Decimal]:
            totals: dict[str, Decimal] = defaultdict(Decimal)
            for r in rows:
                totals[r.brand.name] += r.quantity
            return totals

        return self._compare_sorted(
            by_brand(report_sales),
            by_brand(base_sales),
        )

    async def compare_clients(
        self,
        report_range: DateRange,
        base_range: DateRange,
        filters: SalesFilters | None = None,
    ) -> list[CompareRow]:
        report_sales = await self._sales_in_range(report_range, filters)
        base_sales = await self._sales_in_range(base_range, filters)

        def by_client(rows: list[Sale]) -> dict[str, Decimal]:
            totals: dict[str, Decimal] = defaultdict(Decimal)
            for r in rows:
                totals[r.client.name] += r.quantity
            return totals

        return self._compare_sorted(
            by_client(report_sales),
            by_client(base_sales),
        )

    async def _all_clients_with_stands(self) -> list[Client]:
        if self._clients_with_stands is not None:
            return self._clients_with_stands
        result = await self._session.execute(
            select(Client)
            .options(
                selectinload(Client.manager),
                selectinload(Client.region),
                selectinload(Client.stand_links).selectinload(ClientStand.stand),
            )
        )
        self._clients_with_stands = list(result.scalars().all())
        return self._clients_with_stands

    async def _clients_for_stands(self, filters: ClientFilters | None = None) -> list[Client]:
        clients = await self._all_clients_with_stands()
        if filters is not None:
            clients = filter_clients(clients, filters)
        return clients

    @staticmethod
    def _link_quantity(link: ClientStand) -> int:
        qty = getattr(link, "quantity", 1) or 1
        return max(1, int(qty))

    @classmethod
    def _count_stand_placements(cls, client: Client, *, stand_id: int | None = None) -> int:
        total = 0
        for link in client.stand_links:
            stand = link.stand
            if stand is None or not stand.is_active:
                continue
            if stand_id is not None and link.stand_id != stand_id:
                continue
            total += cls._link_quantity(link)
        return total

    @classmethod
    def _iter_stand_placements(
        cls,
        client: Client,
        *,
        stand_id: int | None = None,
    ):
        for link in client.stand_links:
            stand = link.stand
            if stand is None or not stand.is_active:
                continue
            if stand_id is not None and link.stand_id != stand_id:
                continue
            yield stand.name, cls._link_quantity(link)

    # --- Sales matrix helpers (ported from SK_Account main.js) ---

    @staticmethod
    def _norm_text(value: str) -> str:
        return (
            str(value or "")
            .strip()
            .replace("\u2019", "'")
            .replace("\u2018", "'")
            .replace("`", "'")
        )

    @classmethod
    def _stand_tokens_comparable(cls, a: str, b: str) -> bool:
        def norm(s: str) -> str:
            return " ".join(cls._norm_text(s).split()).lower()

        x = norm(a)
        y = norm(b)
        if not x or not y:
            return False
        if x == y:
            return True

        def tail(s: str) -> str:
            i = s.rfind(":")
            return s if i < 0 else s[i + 1 :].strip()

        tx = tail(x)
        ty = tail(y)
        return tx == y or x == ty or ty == x or y == tx or (tx and ty and tx == ty)

    @classmethod
    def _is_big_product_line(cls, normalized: str) -> bool:
        t = cls._norm_text(normalized)
        return t in {
            "BIG: Carmelita",
            "BIG: Pureloc40",
            "BIG: Novocore Legacy",
            "BIG (невизначено)",
            "BIG",
        }

    @classmethod
    def _sales_matrix_col_key_from_brand(cls, brand_name: str) -> str:
        b = cls._norm_text(brand_name)
        if b.upper() == "BIG":
            return "BIG"
        if b.startswith("BIG:"):
            return "BIG"
        if cls._is_big_product_line(b):
            return "BIG"
        return b

    @classmethod
    def _matrix_col_keys_match(cls, sale_col_key: str, header_col_key: str) -> bool:
        a = cls._norm_text(sale_col_key)
        b = cls._norm_text(header_col_key)
        if not a or not b:
            return False
        if a == b or a.lower() == b.lower():
            return True
        if a == "BIG" and b == "BIG":
            return True
        if a == "BIG" or b == "BIG":
            other = b if a == "BIG" else a
            if other == "BIG":
                return True
            return cls._is_big_product_line(other) or other.startswith("BIG:")
        return cls._stand_tokens_comparable(a, b)

    @classmethod
    def _stand_key_matches_matrix_col(cls, stand_name: str, col_key: str) -> bool:
        s = cls._sales_matrix_col_key_from_brand(stand_name)
        return cls._matrix_col_keys_match(s, col_key) or cls._matrix_col_keys_match(col_key, s)

    @classmethod
    def _client_has_stand_for_col(cls, client: Client, col_key: str) -> bool:
        for link in client.stand_links:
            stand = link.stand
            if stand is None or not stand.is_active:
                continue
            if cls._stand_key_matches_matrix_col(stand.name, col_key):
                return True
        return False

    async def stands_total_by_manager(
        self, filters: ClientFilters | None = None
    ) -> list[StandReportRow]:
        clients = await self._clients_for_stands(filters)
        stand_id = filters.stand_id if filters else None
        counts: dict[str, int] = defaultdict(int)
        for c in clients:
            name = c.manager.name if c.manager else "—"
            counts[name] += self._count_stand_placements(c, stand_id=stand_id)
        return [
            StandReportRow(manager=k, count=v)
            for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        ]

    async def stands_by_manager_and_stand(
        self, filters: ClientFilters | None = None
    ) -> list[StandReportRow]:
        clients = await self._clients_for_stands(filters)
        stand_id = filters.stand_id if filters else None
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for c in clients:
            manager = c.manager.name if c.manager else "—"
            for stand_name, qty in self._iter_stand_placements(c, stand_id=stand_id):
                counts[(manager, stand_name)] += qty
        rows = [
            StandReportRow(manager=m, stand=s, count=n)
            for (m, s), n in counts.items()
        ]
        rows.sort(
            key=lambda r: (
                r.manager or "",
                -r.count,
                (r.stand or "").casefold(),
            )
        )
        return rows

    async def stands_totals_by_city(self, filters: ClientFilters | None = None) -> list[AggRow]:
        clients = await self._clients_for_stands(filters)
        stand_id = filters.stand_id if filters else None
        counts: dict[str, int] = defaultdict(int)
        for c in clients:
            counts[client_city(c)] += self._count_stand_placements(c, stand_id=stand_id)
        return [
            AggRow(label=k, value=Decimal(v))
            for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        ]

    async def stands_by_city_and_stand(
        self, filters: ClientFilters | None = None
    ) -> list[StandReportRow]:
        clients = await self._clients_for_stands(filters)
        stand_id = filters.stand_id if filters else None
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for c in clients:
            city = client_city(c)
            for stand_name, qty in self._iter_stand_placements(c, stand_id=stand_id):
                counts[(city, stand_name)] += qty
        rows = [
            StandReportRow(city=city, stand=stand, count=n)
            for (city, stand), n in counts.items()
        ]
        rows.sort(
            key=lambda r: (
                r.city or "",
                -r.count,
                (r.stand or "").casefold(),
            )
        )
        return rows

    async def stands_totals_by_oblast(self, filters: ClientFilters | None = None) -> list[AggRow]:
        clients = await self._clients_for_stands(filters)
        stand_id = filters.stand_id if filters else None
        counts: dict[str, int] = defaultdict(int)
        for c in clients:
            counts[client_oblast(c)] += self._count_stand_placements(c, stand_id=stand_id)
        return [
            AggRow(label=k, value=Decimal(v))
            for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        ]

    async def stands_by_oblast_and_stand(
        self, filters: ClientFilters | None = None
    ) -> list[StandReportRow]:
        clients = await self._clients_for_stands(filters)
        stand_id = filters.stand_id if filters else None
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for c in clients:
            oblast = client_oblast(c)
            for stand_name, qty in self._iter_stand_placements(c, stand_id=stand_id):
                counts[(oblast, stand_name)] += qty
        rows = [
            StandReportRow(oblast=oblast, stand=stand, count=n)
            for (oblast, stand), n in counts.items()
        ]
        rows.sort(
            key=lambda r: (
                r.oblast or "",
                -r.count,
                (r.stand or "").casefold(),
            )
        )
        return rows

    @classmethod
    def _matching_matrix_cols(cls, stand_name: str, col_keys: list[str]) -> list[str]:
        return [col for col in col_keys if cls._stand_key_matches_matrix_col(stand_name, col)]

    def _matching_matrix_cols_cached(
        self,
        stand_name: str,
        col_keys: list[str],
    ) -> list[str]:
        cache_key = (stand_name, tuple(col_keys))
        if cache_key not in self._stand_col_match_cache:
            self._stand_col_match_cache[cache_key] = self._matching_matrix_cols(
                stand_name, col_keys
            )
        return self._stand_col_match_cache[cache_key]

    def _active_sale_cols_by_client(
        self,
        sales: list[Sale],
        *,
        since: date | None = None,
    ) -> dict[int, set[str]]:
        by_client: dict[int, set[str]] = defaultdict(set)
        for s in sales:
            if since is not None and s.sold_at < since:
                continue
            if s.quantity is None or s.quantity <= 0:
                continue
            by_client[s.client_id].add(self._sales_matrix_col_key_from_brand(s.brand.name))
        return by_client

    def _placement_has_sales_indexed(
        self,
        client_id: int,
        stand_name: str,
        active_by_client: dict[int, set[str]],
    ) -> bool:
        for col in active_by_client.get(client_id, ()):
            if self._stand_key_matches_matrix_col(stand_name, col):
                return True
        return False

    def _inactive_client_label(self, client: Client, name_counts: Counter[str]) -> str:
        name = client.name
        if name_counts[name] <= 1:
            return name
        if client.region and client.region.name:
            return f"{name} · {client.region.name}"
        return f"{name} (#{client.id})"

    async def stands_not_worked(
        self,
        filters: ClientFilters | None = None,
    ) -> tuple[list[InactiveStandRow], list[InactiveStandRow]]:
        """
        Стенди з карток клієнтів без продажів за останні 3 та 6 місяців (як SK_Account).
        """
        clients = await self._clients_for_stands(filters)
        name_counts = Counter(c.name for c in clients)
        rows3: list[InactiveStandRow] = []
        rows6: list[InactiveStandRow] = []

        period3 = rolling_months_range(3)
        period6 = rolling_months_range(6)
        inactive_sales_filter = (
            SalesFilters(manager_id=filters.manager_id) if filters else None
        )
        sales6 = await self._sales_in_range(period6, inactive_sales_filter)
        active6 = self._active_sale_cols_by_client(sales6)
        active3 = self._active_sale_cols_by_client(sales6, since=period3.start)

        for months, bucket, active_index in (
            (3, rows3, active3),
            (6, rows6, active6),
        ):
            period = period3 if months == 3 else period6
            for client in clients:
                manager_name = client.manager.name if client.manager else "—"
                region_name = client.region.name if client.region else "—"
                city = client_city(client)
                oblast = client_oblast(client)
                label = self._inactive_client_label(client, name_counts)
                for link in client.stand_links:
                    stand = link.stand
                    if stand is None or not stand.is_active:
                        continue
                    if filters and filters.stand_id is not None and link.stand_id != filters.stand_id:
                        continue
                    if self._placement_has_sales_indexed(
                        client.id, stand.name, active_index
                    ):
                        continue
                    bucket.append(
                        InactiveStandRow(
                            period_label=period.label,
                            stand_name=stand.name,
                            client_label=label,
                            client_id=client.id,
                            manager_name=manager_name,
                            region_name=region_name,
                            city=city,
                            oblast=oblast,
                            placement_count=1,
                        )
                    )

        def _sort(rows: list[InactiveStandRow]) -> list[InactiveStandRow]:
            return sorted(
                rows,
                key=lambda r: (
                    r.stand_name.casefold(),
                    r.client_label.casefold(),
                    r.manager_name.casefold(),
                ),
            )

        return _sort(rows3), _sort(rows6)

    async def conversion_clients_month(
        self,
        date_range: DateRange,
        manager_id: int | None,
    ) -> list[AggRow]:
        mgr_filter = SalesFilters(manager_id=manager_id) if manager_id else None
        sales = await self._sales_in_range(date_range, mgr_filter)
        clients_with_sales = {s.client_id for s in sales}
        clients = await self._all_clients_with_stands()
        if manager_id is not None:
            clients = [c for c in clients if c.manager_id == manager_id]

        by_manager: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        for c in clients:
            mname = c.manager.name if c.manager else "—"
            total, worked = by_manager[mname]
            total += 1
            if c.id in clients_with_sales:
                worked += 1
            by_manager[mname] = (total, worked)

        rows: list[AggRow] = []
        for name, (total, worked) in sorted(by_manager.items()):
            pct = (worked / total * 100) if total else 0
            rows.append(
                AggRow(
                    label=name,
                    value=Decimal(worked),
                    extra=f"{worked}/{total} ({pct:.0f}%)",
                )
            )
        return rows

    async def conversion_stands_month(
        self,
        date_range: DateRange,
        manager_id: int | None,
    ) -> list[AggRow]:
        mgr_filter = SalesFilters(manager_id=manager_id) if manager_id else None
        sales = await self._sales_in_range(date_range, mgr_filter)
        clients = await self._all_clients_with_stands()
        if manager_id is not None:
            clients = [c for c in clients if c.manager_id == manager_id]

        placements = 0
        worked = 0
        for c in clients:
            for link in c.stand_links:
                placements += 1
                stand_name = link.stand.name
                if any(
                    s.client_id == c.id
                    and (
                        s.brand.name == stand_name
                        or stand_name in s.brand.name
                        or s.brand.name in stand_name
                    )
                    for s in sales
                    if s.client_id == c.id
                ):
                    worked += 1

        pct = (worked / placements * 100) if placements else 0
        return [
            AggRow(
                label="Усі менеджери",
                value=Decimal(worked),
                extra=f"{worked}/{placements} ({pct:.0f}%)",
            )
        ]
