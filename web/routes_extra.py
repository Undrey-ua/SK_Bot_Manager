"""Додаткові маршрути: переміщення стендів, CRUD клієнтів/візитів на вебі."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.storage import StorageError, StorageService
from config.settings import get_settings
from database.models import UserRole, Visit, VisitType
from database.repositories.visit_task_type import VisitTaskTypeRepository
from database.repositories.brand import BrandRepository
from database.repositories.client import ClientRepository
from database.repositories.region import RegionRepository
from database.repositories.stand import StandRepository
from database.repositories.visit import VisitRepository
from web.auth import (
    assert_client_access,
    assert_visit_access,
    require_admin,
    require_nav,
)
from web.deps import query_int, query_str
from web.page_context import load_web_user, page_ctx, scoped_manager_filter
from web.ttl_cache import invalidate_sales_analytics_cache
from web.roles import (
    can_allocate_stand_stock,
    can_filter_managers,
    can_operate_stand_warehouse,
    data_owner_manager_id,
)
from web.services.clients_filter import build_client_filter_options
from web.services.dashboard import DashboardService


@dataclass(frozen=True)
class VisitTaskFormOption:
    code: str
    label: str
    is_active: bool
from web.services.stand_transfer import StandTransferService
from web.client_media import upload_client_cover
from web.utils import (
    UK_MONTHS,
    client_stands_map_json,
    task_label,
    visit_type_label,
    warehouse_stands_map_json,
    warehouse_stands_modal_json,
)


def register_extra_routes(app, *, templates, get_session, require_auth, dashboard_service):
    @app.get("/stands/moves", response_class=HTMLResponse)
    async def stand_moves_history(
        request: Request,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
    ):
        user = await load_web_user(request, session)
        require_nav(user, "stand_moves")
        today = date.today()
        year = query_int(request, "year", default=today.year) or today.year
        month = query_int(request, "month", default=today.month) or today.month
        manager_id = scoped_manager_filter(user, query_int(request, "manager_id"))
        all_clients = await dashboard.list_clients()
        stands = await dashboard.list_active_stands()
        region_id = query_int(request, "region_id")
        city = query_str(request, "city")
        stand_id = query_int(request, "stand_id")

        svc = StandTransferService(session)
        rows = await svc.list_history(
            viewer=user,
            year=year,
            month=month,
            manager_id=manager_id,
            region_id=region_id,
            city=city,
            stand_id=stand_id,
        )
        opts = build_client_filter_options(
            all_clients,
            stands,
            manager_id=manager_id,
            region_id=region_id,
        )
        owner = data_owner_manager_id(user) or user.id
        warehouse_owner = manager_id or owner
        move_clients = (
            all_clients
            if can_filter_managers(user) and manager_id is None
            else [c for c in all_clients if c.manager_id == warehouse_owner]
        )
        stock = await svc.list_warehouse_stock(warehouse_owner)
        return templates.TemplateResponse(
            request,
            "stand_moves.html",
            page_ctx(
                user,
                active_nav="stand_moves",
                rows=rows,
                move_clients=move_clients,
                warehouse_manager_id=warehouse_owner,
                warehouse_stands_json=warehouse_stands_map_json(stock),
                year=year,
                month=month,
                uk_months=UK_MONTHS,
                managers=await dashboard.list_managers() if can_filter_managers(user) else [],
                selected_manager_id=manager_id,
                filter_regions=opts.regions,
                filter_cities=opts.cities,
                filter_stands=opts.stands,
                selected_region_id=region_id,
                selected_city=city,
                selected_stand_id=stand_id,
                client_stands_json=client_stands_map_json(move_clients),
            ),
        )

    @app.post("/stands/move")
    async def stand_move_api(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        from_client_id: int = Form(...),
        stand_id: int = Form(...),
        quantity: int = Form(1),
        to_kind: str = Form(...),
        to_client_id: str = Form(""),
        new_name: str = Form(""),
        new_address: str = Form(""),
        new_city: str = Form(""),
        new_oblast: str = Form(""),
    ):
        user = await load_web_user(request, session)
        if user.is_sales_manager or user.is_leader:
            return JSONResponse(
                {"ok": False, "error": "Немає прав"},
                status_code=403,
            )
        svc = StandTransferService(session)
        try:
            to_cid = int(to_client_id) if to_client_id.strip() else None
            result = await svc.move_stand(
                actor=user,
                from_client_id=from_client_id,
                stand_id=stand_id,
                quantity=quantity,
                to_kind=to_kind,
                to_client_id=to_cid,
                new_name=new_name,
                new_address=new_address,
                new_city=new_city,
                new_oblast=new_oblast,
            )
            await session.commit()
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

        return JSONResponse(
            {
                "ok": True,
                "transfer_id": result.transfer_id,
                "to_client_id": result.to_client_id,
                "to_client_name": result.to_client_name,
            }
        )

    @app.post("/stands/write-off")
    async def stand_write_off_api(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        from_client_id: int = Form(...),
        stand_id: int = Form(...),
        quantity: int = Form(1),
        note: str = Form(""),
    ):
        user = await load_web_user(request, session)
        if user.is_sales_manager or user.is_leader:
            return JSONResponse(
                {"ok": False, "error": "Немає прав"},
                status_code=403,
            )
        svc = StandTransferService(session)
        try:
            result = await svc.write_off_stand(
                actor=user,
                from_client_id=from_client_id,
                stand_id=stand_id,
                quantity=quantity,
                note=note,
            )
            await session.commit()
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

        return JSONResponse({"ok": True, "transfer_id": result.transfer_id})

    def _warehouse_owner_id(user, requested: int | None) -> int:
        owner = data_owner_manager_id(user) or user.id
        if can_filter_managers(user):
            return requested or owner
        return owner

    @app.get("/stands/warehouse", response_class=HTMLResponse)
    async def stand_warehouse_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
    ):
        user = await load_web_user(request, session)
        require_nav(user, "stand_warehouse")
        managers = await dashboard.list_managers() if can_filter_managers(user) else []
        manager_id = scoped_manager_filter(user, query_int(request, "manager_id"))
        is_org_warehouse_view = can_allocate_stand_stock(user)
        show_manager_filter = (
            can_filter_managers(user) and user.role != UserRole.LEADER.value
        )
        show_personal_warehouses = (
            not is_org_warehouse_view
            or (show_manager_filter and manager_id is not None)
        )
        if show_personal_warehouses:
            if can_filter_managers(user) and manager_id is None and managers:
                manager_id = managers[0].id
            owner_id = _warehouse_owner_id(user, manager_id)
        else:
            owner_id = data_owner_manager_id(user) or user.id
        all_clients = await dashboard.list_clients()
        stands = await dashboard.list_active_stands()
        svc = StandTransferService(session)
        manager_warehouse_rows = (
            await svc.list_manager_warehouse_overview(owner_id)
            if show_personal_warehouses
            else []
        )
        central_overview = (
            await svc.list_central_overview() if is_org_warehouse_view else []
        )
        manager_names = {m.id: m.name for m in managers}
        managers_overview = (
            await svc.list_managers_stock_overview(
                [m.id for m in managers],
                manager_names,
            )
            if is_org_warehouse_view and managers
            else []
        )
        opts = build_client_filter_options(
            all_clients,
            stands,
            manager_id=owner_id,
        )
        move_clients = [c for c in all_clients if c.manager_id == owner_id]
        picked = next((m for m in managers if m.id == owner_id), None)
        scope_name = picked.name.split()[0] if picked else user.name.split()[0]
        return templates.TemplateResponse(
            request,
            "stand_warehouse.html",
            page_ctx(
                user,
                active_nav="stand_warehouse",
                manager_warehouse_rows=manager_warehouse_rows,
                central_overview_rows=central_overview,
                managers_overview_rows=managers_overview,
                show_personal_warehouses=show_personal_warehouses,
                show_manager_filter=show_manager_filter,
                warehouse_scope_name=scope_name,
                warehouse_manager_id=owner_id,
                move_clients=move_clients,
                managers=managers,
                selected_manager_id=manager_id,
                filter_stands=opts.stands,
                client_stands_json=client_stands_map_json(move_clients),
                warehouse_stands_json=(
                    warehouse_stands_modal_json(manager_warehouse_rows)
                    if show_personal_warehouses
                    else None
                ),
            ),
        )

    @app.post("/stands/allocate")
    async def stand_allocate_api(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        manager_id: int = Form(...),
        stand_id: int = Form(...),
        quantity: int = Form(1),
        note: str = Form(""),
    ):
        user = await load_web_user(request, session)
        if not can_allocate_stand_stock(user):
            return JSONResponse(
                {"ok": False, "error": "Немає прав"},
                status_code=403,
            )
        svc = StandTransferService(session)
        try:
            result = await svc.allocate_stand_stock(
                actor=user,
                manager_id=manager_id,
                stand_id=stand_id,
                quantity=quantity,
                note=note,
            )
            await session.commit()
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return JSONResponse({"ok": True, "transfer_id": result.transfer_id})

    @app.post("/stands/central/set-total")
    async def stand_central_set_total_api(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        stand_id: int = Form(...),
        total_quantity: int = Form(...),
        note: str = Form(""),
    ):
        user = await load_web_user(request, session)
        if not can_allocate_stand_stock(user):
            return JSONResponse(
                {"ok": False, "error": "Немає прав"},
                status_code=403,
            )
        svc = StandTransferService(session)
        try:
            result = await svc.set_central_total(
                actor=user,
                stand_id=stand_id,
                total_quantity=total_quantity,
                note=note,
            )
            await session.commit()
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return JSONResponse({"ok": True, "transfer_id": result.transfer_id})

    @app.post("/stands/central/to-regional")
    async def stand_central_to_regional_api(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        manager_id: int = Form(...),
        stand_id: int = Form(...),
        quantity: int = Form(1),
        note: str = Form(""),
    ):
        user = await load_web_user(request, session)
        if not can_allocate_stand_stock(user):
            return JSONResponse(
                {"ok": False, "error": "Немає прав"},
                status_code=403,
            )
        svc = StandTransferService(session)
        try:
            result = await svc.transfer_central_to_regional(
                actor=user,
                manager_id=manager_id,
                stand_id=stand_id,
                quantity=quantity,
                note=note,
            )
            await session.commit()
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return JSONResponse({"ok": True, "transfer_id": result.transfer_id})

    @app.post("/stands/to-warehouse")
    async def stand_to_warehouse_api(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        from_client_id: int = Form(...),
        stand_id: int = Form(...),
        quantity: int = Form(1),
        note: str = Form(""),
    ):
        user = await load_web_user(request, session)
        if not can_operate_stand_warehouse(user):
            return JSONResponse(
                {"ok": False, "error": "Немає прав"},
                status_code=403,
            )
        svc = StandTransferService(session)
        try:
            result = await svc.move_to_warehouse(
                actor=user,
                from_client_id=from_client_id,
                stand_id=stand_id,
                quantity=quantity,
                note=note,
            )
            await session.commit()
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return JSONResponse({"ok": True, "transfer_id": result.transfer_id})

    @app.post("/stands/from-warehouse")
    async def stand_from_warehouse_api(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        manager_id: int = Form(...),
        stand_id: int = Form(...),
        quantity: int = Form(1),
        to_kind: str = Form(...),
        to_client_id: str = Form(""),
        new_name: str = Form(""),
        new_address: str = Form(""),
        new_city: str = Form(""),
        new_oblast: str = Form(""),
    ):
        user = await load_web_user(request, session)
        if not can_operate_stand_warehouse(user):
            return JSONResponse(
                {"ok": False, "error": "Немає прав"},
                status_code=403,
            )
        svc = StandTransferService(session)
        try:
            to_cid = int(to_client_id) if to_client_id.strip() else None
            result = await svc.move_from_warehouse(
                actor=user,
                manager_id=manager_id,
                stand_id=stand_id,
                quantity=quantity,
                to_kind=to_kind,
                to_client_id=to_cid,
                new_name=new_name,
                new_address=new_address,
                new_city=new_city,
                new_oblast=new_oblast,
            )
            await session.commit()
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return JSONResponse(
            {
                "ok": True,
                "transfer_id": result.transfer_id,
                "to_client_id": result.to_client_id,
                "to_client_name": result.to_client_name,
            }
        )

    @app.get("/clients/new", response_class=HTMLResponse)
    async def client_new_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
    ):
        user = await load_web_user(request, session)
        require_nav(user, "clients")
        if user.is_leader:
            raise HTTPException(status_code=403, detail="Forbidden")
        managers = []
        form_manager_id = user.id
        if user.is_admin:
            managers = await dashboard.list_managers()
            mgrs = [m for m in managers if m.role == UserRole.MANAGER.value]
            picked = query_int(request, "manager_id")
            if picked is not None:
                form_manager_id = picked
            elif mgrs:
                form_manager_id = mgrs[0].id
        regions = await RegionRepository(session).list_by_manager(form_manager_id)
        stands = await StandRepository(session).list_active()
        brands = await BrandRepository(session).list_active()
        return templates.TemplateResponse(
            request,
            "client_form.html",
            page_ctx(
                user,
                active_nav="clients",
                client=None,
                regions=regions,
                stands=stands,
                brands=brands,
                selected_stand_ids=[],
                selected_swatch_brand_ids=[],
                form_action="/clients/new",
                submit_label="Створити",
                form_manager_id=form_manager_id,
                form_managers=managers,
            ),
        )

    @app.post("/clients/new")
    async def client_new_save(
        request: Request,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
        name: str = Form(...),
        legal_name: str = Form(""),
        region_id: int = Form(...),
        address: str = Form(...),
        city: str = Form(""),
        comment: str = Form(""),
        contacts: str = Form(""),
        stand_id: list[int] = Form(default=[]),
        swatch_brand_id: list[int] = Form(default=[]),
        form_manager_id: str = Form(""),
        cover_photo: UploadFile | None = File(None),
    ):
        user = await load_web_user(request, session)
        require_nav(user, "clients")
        if user.is_leader:
            raise HTTPException(status_code=403, detail="Forbidden")
        stand_ids = stand_id
        swatch_brand_ids = swatch_brand_id
        if not stand_ids and not swatch_brand_ids:
            raise HTTPException(
                status_code=400,
                detail="Оберіть хоча б один стенд або свотч",
            )
        target_manager_id = user.id
        if user.is_admin and form_manager_id.strip().isdigit():
            target_manager_id = int(form_manager_id.strip())

        region = await RegionRepository(session).get_by_id(region_id)
        if region is None or region.manager_id != target_manager_id:
            raise HTTPException(status_code=400, detail="Invalid region")

        from database.repositories.client import ClientRepository

        repo = ClientRepository(session)
        client = await repo.create(
            manager_id=target_manager_id,
            region_id=region_id,
            name=name,
            legal_name=legal_name.strip() or None,
            address=address,
            city=city.strip() or None,
            comment=comment.strip() or None,
            contacts=contacts.strip() or None,
            stand_ids=stand_ids,
            swatch_brand_ids=swatch_brand_ids,
        )
        try:
            photo_url = await upload_client_cover(
                StorageService(get_settings()), client.id, cover_photo
            )
            if photo_url:
                client.photo_url = photo_url
        except StorageError:
            pass
        await session.commit()
        return RedirectResponse(f"/clients/{client.id}", status_code=303)

    @app.get("/clients/{client_id}/edit", response_class=HTMLResponse)
    async def client_edit_page(
        request: Request,
        client_id: int,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
    ):
        user = await load_web_user(request, session)
        require_nav(user, "clients")
        if user.is_leader:
            raise HTTPException(status_code=403, detail="Forbidden")
        await assert_client_access(session, user, client_id)
        client = await dashboard.get_client(client_id)
        if client is None:
            raise HTTPException(status_code=404)
        regions = await RegionRepository(session).list_by_manager(client.manager_id)
        stands = await StandRepository(session).list_active()
        brands = await BrandRepository(session).list_active()
        selected = [link.stand_id for link in client.stand_links]
        selected_swatches = [link.brand_id for link in client.swatch_links]
        return templates.TemplateResponse(
            request,
            "client_form.html",
            page_ctx(
                user,
                active_nav="clients",
                client=client,
                regions=regions,
                stands=stands,
                brands=brands,
                selected_stand_ids=selected,
                selected_swatch_brand_ids=selected_swatches,
                form_action=f"/clients/{client_id}/edit",
                submit_label="Зберегти",
            ),
        )

    @app.post("/clients/{client_id}/edit")
    async def client_edit_save(
        request: Request,
        client_id: int,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
        name: str = Form(...),
        legal_name: str = Form(""),
        region_id: int = Form(...),
        address: str = Form(...),
        city: str = Form(""),
        comment: str = Form(""),
        contacts: str = Form(""),
        stand_id: list[int] = Form(default=[]),
        swatch_brand_id: list[int] = Form(default=[]),
        cover_photo: UploadFile | None = File(None),
        remove_photo: str = Form(""),
    ):
        user = await load_web_user(request, session)
        require_nav(user, "clients")
        if user.is_leader:
            raise HTTPException(status_code=403, detail="Forbidden")
        await assert_client_access(session, user, client_id)
        client = await dashboard.get_client(client_id)
        if client is None:
            raise HTTPException(status_code=404)
        stand_ids = stand_id
        swatch_brand_ids = swatch_brand_id
        if not stand_ids and not swatch_brand_ids:
            raise HTTPException(
                status_code=400,
                detail="Оберіть хоча б один стенд або свотч",
            )
        region = await RegionRepository(session).get_by_id(region_id)
        if region is None or region.manager_id != client.manager_id:
            raise HTTPException(status_code=400)

        from database.repositories.client import ClientRepository

        photo_url = client.photo_url
        update_photo = False
        if remove_photo.strip() in ("1", "true", "yes", "on"):
            photo_url = None
            update_photo = True
        else:
            try:
                uploaded = await upload_client_cover(
                    StorageService(get_settings()), client_id, cover_photo
                )
                if uploaded:
                    photo_url = uploaded
                    update_photo = True
            except StorageError:
                pass

        await ClientRepository(session).update(
            client_id,
            region_id=region_id,
            name=name,
            legal_name=legal_name.strip() or None,
            address=address,
            city=city.strip() or None,
            comment=comment.strip() or None,
            stand_ids=stand_ids,
            contacts=contacts.strip() or None,
            photo_url=photo_url,
            update_photo=update_photo,
            swatch_brand_ids=swatch_brand_ids,
        )
        await session.commit()
        return RedirectResponse(f"/clients/{client_id}", status_code=303)

    @app.post("/clients/{client_id}/delete")
    async def client_delete(
        request: Request,
        client_id: int,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ):
        user = await load_web_user(request, session)
        require_nav(user, "clients")
        if user.is_leader:
            raise HTTPException(status_code=403, detail="Forbidden")
        await assert_client_access(session, user, client_id)
        deleted = await ClientRepository(session).delete(client_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Клієнта не знайдено")
        await session.commit()
        invalidate_sales_analytics_cache()
        return RedirectResponse("/clients?deleted=1", status_code=303)

    @app.get("/visits/{visit_id}/edit", response_class=HTMLResponse)
    async def visit_edit_page(
        request: Request,
        visit_id: int,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
    ):
        user = await load_web_user(request, session)
        require_nav(user, "visits")
        await assert_visit_access(session, user, visit_id)
        visit = await dashboard.get_visit(visit_id)
        if visit is None:
            raise HTTPException(status_code=404)
        task_values = [t.task for t in visit.tasks]
        rows = await VisitTaskTypeRepository(session).list_all()
        known_codes = {row.code for row in rows}
        task_options = [
            VisitTaskFormOption(row.code, row.label, row.is_active) for row in rows
        ]
        for code in task_values:
            if code not in known_codes:
                task_options.append(
                    VisitTaskFormOption(code, task_label(code), False)
                )
        return templates.TemplateResponse(
            request,
            "visit_edit.html",
            page_ctx(
                user,
                active_nav="visits",
                visit=visit,
                task_types=task_options,
                selected_tasks=task_values,
            ),
        )

    @app.post("/visits/{visit_id}/edit")
    async def visit_edit_save(
        request: Request,
        visit_id: int,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        visit_type: str = Form(...),
        comment: str = Form(""),
        task: list[str] = Form(default=[]),
    ):
        user = await load_web_user(request, session)
        require_nav(user, "visits")
        await assert_visit_access(session, user, visit_id)
        visit = await VisitRepository(session).get_by_id(visit_id)
        if visit is None:
            raise HTTPException(status_code=404)
        if visit_type not in {v.value for v in VisitType}:
            raise HTTPException(status_code=400)
        allowed_codes = {row.code for row in await VisitTaskTypeRepository(session).list_all()}
        tasks = [x for x in task if x in allowed_codes]
        visit.visit_type = visit_type
        visit.comment = comment.strip() or None
        for vt in list(visit.tasks):
            await session.delete(vt)
        await session.flush()
        from database.models import VisitTask

        for t in tasks:
            session.add(VisitTask(visit_id=visit.id, task=t))
        await session.commit()
        return RedirectResponse(f"/visits/{visit_id}", status_code=303)
