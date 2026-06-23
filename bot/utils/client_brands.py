from __future__ import annotations

from database.models import Brand, Client
from utils.stand_brand_match import stand_matches_brand

# Лінійки всередині стенду BIG (назви в таблиці brands)
BIG_PRODUCT_BRAND_NAMES: tuple[str, ...] = (
    "BIG: Carmelita",
    "BIG: Pureloc40",
    "BIG: Novocore Legacy",
)


def _norm(s: str) -> str:
    return " ".join(s.strip().split())


def is_big_stand(stand_name: str) -> bool:
    u = _norm(stand_name).upper()
    return u == "BIG" or u.startswith("BIG:")


def _brand_for_stand_name(stand_name: str, brands: list[Brand]) -> Brand | None:
    sn = _norm(stand_name)
    for brand in brands:
        if not brand.is_active:
            continue
        if _norm(brand.name).lower() == sn.lower():
            return brand
        if stand_matches_brand(stand_name, brand.name):
            return brand
    return None


def stand_covered_by_brands(stand_name: str, brands: list[Brand]) -> bool:
    if is_big_stand(stand_name):
        return bool(_big_brands_for_stand(stand_name, {b.name: b for b in brands}))
    return _brand_for_stand_name(stand_name, brands) is not None


def _big_brands_for_stand(stand_name: str, brand_by_name: dict[str, Brand]) -> list[Brand]:
    sn = _norm(stand_name)
    if sn.upper() == "BIG":
        out: list[Brand] = []
        for name in BIG_PRODUCT_BRAND_NAMES:
            b = brand_by_name.get(name)
            if b and b.is_active:
                out.append(b)
        return out
    matched = _brand_for_stand_name(stand_name, list(brand_by_name.values()))
    return [matched] if matched else []


def brands_from_stands(client: Client, all_brands: list[Brand]) -> list[Brand]:
    """Бренди, доступні за стендами клієнта."""
    active_brands = [b for b in all_brands if b.is_active]
    brand_by_name = {b.name: b for b in active_brands}
    seen: set[int] = set()
    result: list[Brand] = []

    stands = [
        link.stand
        for link in client.stand_links
        if link.stand is not None and link.stand.is_active
    ]
    for stand in stands:
        if is_big_stand(stand.name):
            for brand in _big_brands_for_stand(stand.name, brand_by_name):
                if brand.id not in seen:
                    seen.add(brand.id)
                    result.append(brand)
        else:
            brand = _brand_for_stand_name(stand.name, active_brands)
            if brand and brand.id not in seen:
                seen.add(brand.id)
                result.append(brand)

    return sorted(result, key=lambda b: (b.sort_order, b.name))


def brands_from_swatches(client: Client, all_brands: list[Brand]) -> list[Brand]:
    """Бренди, для яких на ТТ є нарізки зразків (свотчі)."""
    active_by_id = {b.id: b for b in all_brands if b.is_active}
    result: list[Brand] = []
    seen: set[int] = set()
    for link in getattr(client, "swatch_links", ()):
        brand = link.brand if link.brand is not None else active_by_id.get(link.brand_id)
        if brand is None or not brand.is_active or brand.id in seen:
            continue
        seen.add(brand.id)
        result.append(brand)
    return sorted(result, key=lambda b: (b.sort_order, b.name))


def brands_for_client(client: Client, all_brands: list[Brand]) -> list[Brand]:
    """Бренди для продажу: стенди + свотчі."""
    seen: set[int] = set()
    result: list[Brand] = []
    for brand in brands_from_stands(client, all_brands) + brands_from_swatches(
        client, all_brands
    ):
        if brand.id not in seen:
            seen.add(brand.id)
            result.append(brand)
    return sorted(result, key=lambda b: (b.sort_order, b.name))


def sale_is_from_swatch(client: Client, brand_id: int, all_brands: list[Brand]) -> bool:
    """Продаж зі свотчу, якщо бренд є в свотчах і не покритий стендом."""
    stand_ids = {b.id for b in brands_from_stands(client, all_brands)}
    if brand_id in stand_ids:
        return False
    swatch_ids = {b.id for b in brands_from_swatches(client, all_brands)}
    return brand_id in swatch_ids


def brand_button_label(brand: Brand) -> str:
    if brand.name.startswith("BIG: "):
        label = brand.name[5:]
        if label.endswith(" Legacy"):
            return label[: -len(" Legacy")]
        return label
    return brand.name
