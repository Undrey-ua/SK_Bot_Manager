"""JSON API для каскадних форм (резерви, продажі)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.client_brands import brand_button_label, brands_for_client
from config.team import filter_regional_managers
from database.repositories.brand import BrandRepository
from database.repositories.client import ClientRepository
from database.repositories.region import RegionRepository
from database.repositories.reserve import ReserveRepository
from database.repositories.user import UserRepository
from web.deps import query_int
from web.page_context import load_web_user
from web.roles import (
    can_pick_reserve_manager,
    can_sale_from_reserve,
    form_owner_manager_id,
    nav_allowed,
    resolve_reserve_form_manager_id,
)


def _require_form_nav(user) -> None:
    if not (nav_allowed(user, "reserves") or nav_allowed(user, "analytics")):
        raise HTTPException(status_code=403, detail="Forbidden")


async def _validated_form_manager_id(
    session: AsyncSession,
    user,
    requested: int | None,
) -> int:
    try:
        manager_id = resolve_reserve_form_manager_id(user, requested)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Оберіть менеджера") from exc

    if can_pick_reserve_manager(user):
        users = filter_regional_managers(await UserRepository(session).list_all())
        allowed = {u.id for u in users}
        if manager_id not in allowed:
            raise HTTPException(status_code=400, detail="Невірний менеджер")
    return manager_id


def register_form_api_routes(
    app,
    *,
    get_session,
    require_auth,
):
    @app.get("/api/form/managers")
    async def api_form_managers(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> JSONResponse:
        user = await load_web_user(request, session)
        _require_form_nav(user)
        if not can_pick_reserve_manager(user):
            raise HTTPException(status_code=403, detail="Forbidden")
        managers = filter_regional_managers(await UserRepository(session).list_all())
        return JSONResponse([{"id": m.id, "name": m.name} for m in managers])

    @app.get("/api/form/regions")
    async def api_form_regions(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> JSONResponse:
        user = await load_web_user(request, session)
        _require_form_nav(user)
        requested = query_int(request, "manager_id")
        if can_pick_reserve_manager(user) and requested is None:
            return JSONResponse([])
        manager_id = await _validated_form_manager_id(session, user, requested)
        regions = await RegionRepository(session).list_by_manager(manager_id)
        return JSONResponse([{"id": r.id, "name": r.name} for r in regions])

    @app.get("/api/form/clients")
    async def api_form_clients(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> JSONResponse:
        user = await load_web_user(request, session)
        _require_form_nav(user)
        region_id = query_int(request, "region_id")
        if region_id is None:
            raise HTTPException(status_code=400, detail="region_id required")

        requested = query_int(request, "manager_id")
        manager_id = await _validated_form_manager_id(session, user, requested)
        region = await RegionRepository(session).get_by_id(region_id)
        if region is None or region.manager_id != manager_id:
            raise HTTPException(status_code=404, detail="Область не знайдена")

        clients = await ClientRepository(session).list_by_manager_and_region(
            manager_id, region_id
        )
        return JSONResponse([{"id": c.id, "name": c.name} for c in clients])

    @app.get("/api/form/brands")
    async def api_form_brands(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> JSONResponse:
        user = await load_web_user(request, session)
        _require_form_nav(user)
        client_id = query_int(request, "client_id")
        if client_id is None:
            raise HTTPException(status_code=400, detail="client_id required")

        manager_id = form_owner_manager_id(user)
        client = await ClientRepository(session).get_by_id(client_id)
        if client is None or client.manager_id != manager_id:
            raise HTTPException(status_code=404, detail="Клієнта не знайдено")

        all_brands = await BrandRepository(session).list_active()
        matched = brands_for_client(client, all_brands)
        return JSONResponse(
            [{"id": b.id, "name": brand_button_label(b)} for b in matched]
        )

    @app.get("/api/reserves/{reserve_id}/brands")
    async def api_reserve_brands(
        reserve_id: int,
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> JSONResponse:
        user = await load_web_user(request, session)
        _require_form_nav(user)

        reserve = await ReserveRepository(session).get_by_id(reserve_id)
        if reserve is None or reserve.cancelled_at is not None:
            raise HTTPException(status_code=404, detail="Резерв не знайдено")
        if not can_sale_from_reserve(user, manager_id=reserve.manager_id):
            raise HTTPException(status_code=403, detail="Forbidden")

        client = await ClientRepository(session).get_by_id(reserve.client_id)
        if client is None:
            raise HTTPException(status_code=404, detail="Клієнта не знайдено")

        all_brands = await BrandRepository(session).list_active()
        matched = brands_for_client(client, all_brands)
        return JSONResponse(
            {
                "reserve_id": reserve.id,
                "client_name": client.name,
                "reserve_qty": str(reserve.quantity),
                "material": reserve.material,
                "brands": [
                    {"id": b.id, "name": brand_button_label(b)} for b in matched
                ],
            }
        )
