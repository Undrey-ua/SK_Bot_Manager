"""Редагування назв областей (лише адмін)."""

from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories.region import RegionRepository
from web.auth import require_admin
from web.page_context import load_web_user, page_ctx

_SEPARATORS = re.compile(r"[\s\-\u2010\u2011\u2012\u2013\u2014_.'’`]+")


def _fold_region_name(name: str) -> str:
    return _SEPARATORS.sub("", name.casefold())


def _redirect(message: str | None = None, *, ok: str | None = None) -> RedirectResponse:
    if message:
        return RedirectResponse(f"/admin/regions?error={quote(message)}", status_code=303)
    return RedirectResponse(f"/admin/regions?{ok}=1", status_code=303)


def register_region_routes(app, *, templates, get_session, require_auth):
    @app.get("/admin/regions", response_class=HTMLResponse)
    async def regions_admin_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_admin(user)
        repo = RegionRepository(session)
        regions = await repo.list_all()
        counts = await repo.usage_counts()

        by_manager: dict[int, list] = {}
        for region in regions:
            by_manager.setdefault(region.manager_id, []).append(region)

        groups = []
        for manager_regions in by_manager.values():
            folded: dict[str, int] = {}
            for region in manager_regions:
                key = _fold_region_name(region.name)
                folded[key] = folded.get(key, 0) + 1
            manager_regions.sort(key=lambda item: item.name.casefold())
            manager = manager_regions[0].manager
            rows = []
            for region in manager_regions:
                clients, reserves = counts.get(region.id, (0, 0))
                folded_name = _fold_region_name(region.name)
                siblings = [
                    {"id": other.id, "name": other.name}
                    for other in manager_regions
                    if other.id != region.id
                ]
                siblings.sort(
                    key=lambda other: (
                        0 if _fold_region_name(other["name"]) == folded_name else 1,
                        other["name"].casefold(),
                    )
                )
                rows.append(
                    {
                        "id": region.id,
                        "name": region.name,
                        "client_count": clients,
                        "reserve_count": reserves,
                        "duplicate": folded.get(folded_name, 0) > 1,
                        "siblings": siblings,
                    }
                )
            groups.append(
                {
                    "manager_name": manager.name if manager is not None else "—",
                    "rows": rows,
                }
            )
        groups.sort(key=lambda item: str(item["manager_name"]).casefold())

        qp = request.query_params
        return templates.TemplateResponse(
            request,
            "regions_admin.html",
            page_ctx(
                user,
                active_nav="regions",
                groups=groups,
                renamed=qp.get("renamed") == "1",
                merged=qp.get("merged") == "1",
                deleted=qp.get("deleted") == "1",
                error=qp.get("error") or None,
            ),
        )

    @app.post("/admin/regions/{region_id}/rename")
    async def region_rename(
        request: Request,
        region_id: int,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        name: str = Form(""),
    ) -> RedirectResponse:
        user = await load_web_user(request, session)
        require_admin(user)
        cleaned = name.strip()
        if not cleaned:
            return _redirect("Назва області не може бути порожньою.")
        if len(cleaned) > 100:
            return _redirect("Назва області має бути не довшою за 100 символів.")

        repo = RegionRepository(session)
        region = await repo.get_by_id(region_id)
        if region is None:
            return _redirect("Область не знайдено.")
        if region.name == cleaned:
            return _redirect(ok="renamed")
        try:
            await repo.rename(region, cleaned)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return _redirect(
                f"Область «{cleaned}» уже є в цього менеджера. "
                "Об'єднайте дубль, щоб перенести клієнтів і резерви."
            )
        return _redirect(ok="renamed")

    @app.post("/admin/regions/{region_id}/merge")
    async def region_merge(
        request: Request,
        region_id: int,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        target_id: str = Form(""),
    ) -> RedirectResponse:
        user = await load_web_user(request, session)
        require_admin(user)
        if not target_id.strip().isdigit():
            return _redirect("Оберіть область, з якою об'єднати.")
        target = int(target_id)
        if target == region_id:
            return _redirect("Не можна об'єднати область саму з собою.")

        repo = RegionRepository(session)
        source = await repo.get_by_id(region_id)
        destination = await repo.get_by_id(target)
        if source is None or destination is None:
            return _redirect("Область не знайдено.")
        if source.manager_id != destination.manager_id:
            return _redirect("Об'єднувати можна лише області одного менеджера.")
        await repo.merge(source, destination)
        await session.commit()
        return _redirect(ok="merged")

    @app.post("/admin/regions/{region_id}/delete")
    async def region_delete(
        request: Request,
        region_id: int,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> RedirectResponse:
        user = await load_web_user(request, session)
        require_admin(user)
        repo = RegionRepository(session)
        region = await repo.get_by_id(region_id)
        if region is None:
            return _redirect("Область не знайдено.")
        counts = await repo.usage_counts()
        clients, reserves = counts.get(region.id, (0, 0))
        if clients or reserves:
            return _redirect(
                "Область використовується. Перейменуйте її або об'єднайте з правильною."
            )
        try:
            await repo.delete(region)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return _redirect(
                "Область використовується. Перейменуйте її або об'єднайте з правильною."
            )
        return _redirect(ok="deleted")
