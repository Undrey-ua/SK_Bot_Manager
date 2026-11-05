"""Каталог торгових марок BIG і Tarkett та порівняння після поділу лінійок.

Стенди не змінюються: BIG і Tarkett SPC. Нові продажі пишуться на окремі марки.
Минулі продажі лишаються на старих марках — їх не розкладаємо заднім числом.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


BIG_SALE_BRANDS: tuple[str, ...] = (
    "BIG: Carmelita",
    "BIG: Pureloc40",
    "BIG: Novocore LVT",
    "BIG: Novocore LVT HB",
    "BIG: Novocore SPC",
    "BIG: Novocore SPC HB",
)

TARKETT_SALE_BRANDS: tuple[str, ...] = (
    "Tarkett: SPC Living 55",
    "Tarkett: SPC Herringbone 55",
)

ACTIVE_SALE_BRANDS: tuple[tuple[str, int], ...] = (
    ("BIG: Carmelita", 1),
    ("BIG: Pureloc40", 2),
    ("BIG: Novocore LVT", 3),
    ("BIG: Novocore LVT HB", 4),
    ("BIG: Novocore SPC", 5),
    ("BIG: Novocore SPC HB", 6),
    ("Tarkett: SPC Living 55", 7),
    ("Tarkett: SPC Herringbone 55", 8),
)

NOVOCORE_LEGACY_NAMES: tuple[str, ...] = (
    "BIG: Novocore Legacy",
    "BIG: Novocore",
    "Novocore Legacy",
    "Novocore",
)

TARKETT_LEGACY_NAMES: tuple[str, ...] = (
    "Tarkett SPC",
    "Tarkett",
)

_LABEL_OVERRIDES = {
    "tarkett: express": "Tarkett Express",
    "tarkett living": "Tarkett Living",
    "tarkett herringbone": "Tarkett Herringbone",
    "tarkett spc": "Tarkett SPC",
    "tarkett": "Tarkett",
}


def name_key(name: str) -> str:
    return " ".join((name or "").strip().split()).casefold()


def trade_mark_label(name: str) -> str:
    """Коротка назва марки для кнопок, фільтрів і звітів."""
    raw = " ".join((name or "").strip().split())
    if not raw:
        return raw
    key = name_key(raw)
    if key in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[key]
    low = key
    for prefix in ("big: ", "tarkett: "):
        if low.startswith(prefix):
            raw = raw[len(prefix) :]
            low = name_key(raw)
            break
    if low.endswith(" legacy"):
        raw = raw[: -len(" Legacy")].rstrip()
    return raw


def stand_column_for_name(name: str) -> str | None:
    """Колонка стенду для матриці і «спрацювавших» стендів. None — окрема марка."""
    raw = " ".join((name or "").strip().split())
    if not raw:
        return None
    upper = raw.upper()
    if upper == "BIG" or upper.startswith("BIG:") or upper.startswith("BIG "):
        return "BIG"
    low = name_key(raw)
    if low in {"tarkett", "tarkett spc"} or low.startswith("tarkett: spc"):
        return "Tarkett SPC"
    return None


def is_tarkett_stand(stand_name: str) -> bool:
    return name_key(stand_name) in {"tarkett", "tarkett spc"}


class SplitFamily:
    def __init__(
        self,
        label: str,
        legacy: tuple[str, ...],
        children: tuple[str, ...],
    ) -> None:
        self.label = label
        self.legacy = legacy
        self.children = children
        self._legacy = {name_key(n) for n in legacy}
        self._children = {name_key(n) for n in children}
        self._child_index = {name_key(n): i for i, n in enumerate(children)}

    def matches(self, name: str) -> bool:
        key = name_key(name)
        return key in self._legacy or key in self._children

    def is_child(self, name: str) -> bool:
        return name_key(name) in self._children

    def is_legacy(self, name: str) -> bool:
        return name_key(name) in self._legacy

    def detail_rank(self, name: str) -> tuple[int, int, str]:
        key = name_key(name)
        if key in self._child_index:
            return (0, self._child_index[key], trade_mark_label(name).casefold())
        return (1, 0, trade_mark_label(name).casefold())


SPLIT_FAMILIES: tuple[SplitFamily, ...] = (
    SplitFamily("Novocore", NOVOCORE_LEGACY_NAMES, BIG_SALE_BRANDS[2:]),
    SplitFamily("Tarkett SPC", TARKETT_LEGACY_NAMES, TARKETT_SALE_BRANDS),
)


def is_historical_unsplit(name: str) -> bool:
    return any(family.is_legacy(name) for family in SPLIT_FAMILIES)


def brand_filter_choices(brands: Iterable[Any]) -> list[tuple[int, str]]:
    """Активні марки і старі нерозділені, щоб фільтр бачив минулі продажі."""
    rows: list[tuple[int, int, str]] = []
    for brand in brands:
        active = bool(getattr(brand, "is_active", True))
        if not active and not is_historical_unsplit(brand.name):
            continue
        label = trade_mark_label(brand.name)
        if not active:
            label = f"{label} (до поділу)"
        rows.append((int(brand.sort_order or 0), int(brand.id), label))
    rows.sort(key=lambda item: (item[0], item[2].casefold()))
    return [(brand_id, label) for _, brand_id, label in rows]


@dataclass(frozen=True)
class BrandCompareLine:
    label: str
    current: Decimal
    previous: Decimal
    detail: bool = False
    grouped: bool = False


def build_brand_compare_lines(
    current: Mapping[str, Decimal],
    previous: Mapping[str, Decimal],
) -> list[BrandCompareLine]:
    """Порівняння марок.

    Поки в обох періодах лише стара нерозділена марка, рядок лишається як був.
    Якщо з'явилась нова лінійка, сума родини порівнюється з минулим, а склад
    показано окремими рядками (їх не треба додавати до суми ще раз).
    """
    names = set(current) | set(previous)
    consumed: set[str] = set()
    groups: list[list[BrandCompareLine]] = []

    for family in SPLIT_FAMILIES:
        members = [name for name in names if family.matches(name)]
        if not members:
            continue
        if not any(family.is_child(name) for name in members) or len(members) == 1:
            continue
        consumed.update(name_key(name) for name in members)
        current_total = sum((current.get(name, Decimal(0)) for name in members), Decimal(0))
        previous_total = sum(
            (previous.get(name, Decimal(0)) for name in members),
            Decimal(0),
        )
        details = [
            BrandCompareLine(
                label=(
                    f"{trade_mark_label(name)} (до поділу)"
                    if family.is_legacy(name)
                    else trade_mark_label(name)
                ),
                current=current.get(name, Decimal(0)),
                previous=previous.get(name, Decimal(0)),
                detail=True,
            )
            for name in sorted(members, key=family.detail_rank)
        ]
        groups.append(
            [
                BrandCompareLine(
                    label=family.label,
                    current=current_total,
                    previous=previous_total,
                    grouped=True,
                ),
                *details,
            ]
        )

    buckets_current: dict[str, Decimal] = defaultdict(Decimal)
    buckets_previous: dict[str, Decimal] = defaultdict(Decimal)
    for name in names:
        if name_key(name) in consumed:
            continue
        label = trade_mark_label(name)
        buckets_current[label] += current.get(name, Decimal(0))
        buckets_previous[label] += previous.get(name, Decimal(0))
    for label in set(buckets_current) | set(buckets_previous):
        groups.append(
            [
                BrandCompareLine(
                    label=label,
                    current=buckets_current.get(label, Decimal(0)),
                    previous=buckets_previous.get(label, Decimal(0)),
                )
            ]
        )

    groups.sort(
        key=lambda group: (group[0].current, group[0].label.casefold()),
        reverse=True,
    )
    return [line for group in groups for line in group]
