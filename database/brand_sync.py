"""Ідемпотентне оновлення марок BIG і Tarkett. Продажі не переписуються."""

from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Brand, ClientSwatch
from utils.brand_catalog import (
    ACTIVE_SALE_BRANDS,
    BIG_SALE_BRANDS,
    NOVOCORE_LEGACY_NAMES,
    TARKETT_LEGACY_NAMES,
    TARKETT_SALE_BRANDS,
)

logger = logging.getLogger(__name__)

_PROTECTED_SORT = {name for name, _sort in ACTIVE_SALE_BRANDS}
_RETIRED = NOVOCORE_LEGACY_NAMES + TARKETT_LEGACY_NAMES


async def sync_brand_split(session: AsyncSession) -> None:
    brands = list((await session.scalars(select(Brand))).all())
    by_name = {brand.name: brand for brand in brands}

    for name, sort_order in ACTIVE_SALE_BRANDS:
        brand = by_name.get(name)
        if brand is None:
            brand = Brand(name=name, sort_order=sort_order, is_active=True)
            session.add(brand)
            by_name[name] = brand
        else:
            if not brand.is_active:
                brand.is_active = True
            if brand.sort_order != sort_order:
                brand.sort_order = sort_order

    await session.flush()

    for brand in by_name.values():
        if brand.name in _PROTECTED_SORT:
            continue
        if brand.is_active and 0 < brand.sort_order <= 11:
            brand.sort_order += 20

    await _replace_swatches(
        session,
        by_name,
        source_names=NOVOCORE_LEGACY_NAMES,
        target_names=BIG_SALE_BRANDS[2:],
    )
    await _replace_swatches(
        session,
        by_name,
        source_names=TARKETT_LEGACY_NAMES,
        target_names=TARKETT_SALE_BRANDS,
    )

    for name in _RETIRED:
        brand = by_name.get(name)
        if brand is None:
            continue
        if brand.is_active or brand.sort_order != 200:
            brand.is_active = False
            brand.sort_order = 200

    await session.flush()
    logger.info("Brand split synced")


async def _replace_swatches(
    session: AsyncSession,
    by_name: dict[str, Brand],
    *,
    source_names: tuple[str, ...],
    target_names: tuple[str, ...],
) -> None:
    sources = [by_name[name] for name in source_names if name in by_name]
    targets = [by_name[name] for name in target_names if name in by_name]
    if not sources or not targets:
        return

    source_ids = [brand.id for brand in sources]
    swatches = list(
        (
            await session.scalars(
                select(ClientSwatch).where(ClientSwatch.brand_id.in_(source_ids))
            )
        ).all()
    )
    client_ids = {row.client_id for row in swatches}
    if client_ids and targets:
        existing = {
            (row.client_id, row.brand_id)
            for row in (
                await session.scalars(
                    select(ClientSwatch).where(ClientSwatch.client_id.in_(client_ids))
                )
            ).all()
        }
        for client_id in client_ids:
            for target in targets:
                key = (client_id, target.id)
                if key in existing:
                    continue
                session.add(ClientSwatch(client_id=client_id, brand_id=target.id))
                existing.add(key)
        await session.flush()

    if source_ids:
        await session.execute(
            delete(ClientSwatch).where(ClientSwatch.brand_id.in_(source_ids))
        )
