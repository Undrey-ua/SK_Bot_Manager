from __future__ import annotations

from dataclasses import dataclass

from database.models import Brand, Client, Stand
from web.client_geo import client_city


@dataclass(frozen=True)
class ClientFilterOptions:
    regions: list[tuple[int, str]]
    cities: list[str]
    stands: list[tuple[int, str]]


@dataclass(frozen=True)
class SalesFilterOptions(ClientFilterOptions):
    brands: list[tuple[int, str]]


@dataclass(frozen=True)
class ClientFilters:
    manager_id: int | None = None
    region_id: int | None = None
    city: str | None = None
    stand_id: int | None = None
    is_potential: bool | None = None


@dataclass(frozen=True)
class SalesFilters(ClientFilters):
    brand_id: int | None = None


def sales_filters_to_client(filters: SalesFilters | None) -> ClientFilters | None:
    if filters is None:
        return None
    return ClientFilters(
        manager_id=filters.manager_id,
        region_id=filters.region_id,
        city=filters.city,
        stand_id=filters.stand_id,
        is_potential=filters.is_potential,
    )


def sales_filters_active(filters: SalesFilters | None) -> bool:
    if filters is None:
        return False
    return any(
        [
            filters.manager_id is not None,
            filters.region_id is not None,
            filters.city,
            filters.stand_id is not None,
            filters.brand_id is not None,
        ]
    )


def _client_stand_ids(client: Client) -> set[int]:
    return {
        link.stand_id
        for link in client.stand_links
        if link.stand_id is not None
    }


def client_matches_filters(client: Client, filters: ClientFilters) -> bool:
    if filters.manager_id is not None and client.manager_id != filters.manager_id:
        return False
    if filters.region_id is not None and client.region_id != filters.region_id:
        return False
    if filters.city:
        if client_city(client) != filters.city:
            return False
    if filters.stand_id is not None:
        if filters.stand_id not in _client_stand_ids(client):
            return False
    if filters.is_potential is not None and client.is_potential != filters.is_potential:
        return False
    return True


def filter_clients(clients: list[Client], filters: ClientFilters) -> list[Client]:
    return [c for c in clients if client_matches_filters(c, filters)]


def build_client_filter_options(
    clients: list[Client],
    stands: list[Stand],
    *,
    manager_id: int | None = None,
    region_id: int | None = None,
) -> ClientFilterOptions:
    """Опції для випадаючих списків з урахуванням уже обраних фільтрів."""
    pool = clients
    if manager_id is not None:
        pool = [c for c in pool if c.manager_id == manager_id]

    regions: dict[int, str] = {}
    cities: set[str] = set()
    for c in pool:
        if c.region:
            regions[c.region.id] = c.region.name
        if region_id is not None and c.region_id != region_id:
            continue
        city = client_city(c)
        if city and city != "—":
            cities.add(city)

    return ClientFilterOptions(
        regions=sorted(regions.items(), key=lambda x: x[1].casefold()),
        cities=sorted(cities, key=str.casefold),
        stands=[(s.id, s.name) for s in stands if s.is_active],
    )


def build_sales_filter_options(
    clients: list[Client],
    stands: list[Stand],
    brands: list[Brand],
    *,
    manager_id: int | None = None,
    region_id: int | None = None,
) -> SalesFilterOptions:
    base = build_client_filter_options(
        clients,
        stands,
        manager_id=manager_id,
        region_id=region_id,
    )
    return SalesFilterOptions(
        regions=base.regions,
        cities=base.cities,
        stands=base.stands,
        brands=[(b.id, b.name) for b in brands if b.is_active],
    )
