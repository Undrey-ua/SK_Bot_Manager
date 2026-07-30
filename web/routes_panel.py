"""Аналітика, резерви та задачі веб-панелі."""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.notifications.reserve_broadcast import broadcast_new_reserve
from bot.notifications.task_assign import notify_task_assigned
from config.settings import Settings
from database.models import (
    ManagerTaskKind,
    Reserve,
    Task,
    User,
    UserRole,
    normalize_manager_task_kind,
)
from database.repositories.client import ClientRepository
from database.repositories.region import RegionRepository
from database.repositories.reserve import ReserveRepository
from database.repositories.sale import SaleRepository
from database.repositories.user import UserRepository
from web.analytics_periods import (
    month_range,
    prev_month_range,
    quarter_range,
    year_range,
)
from web.auth import (
    assert_reserve_manage_access,
    assert_sale_manage_access,
    assert_task_manage_access,
    require_nav,
    require_reserve_create,
    require_sale_create,
    require_task_create,
)
from web.deps import query_int, query_str
from web.page_context import load_web_user, page_ctx, scoped_manager_filter
from config.team import filter_regional_managers
from web.roles import (
    can_filter_managers,
    can_filter_reserves_managers,
    can_manage_sale,
    can_manage_sales_plans,
    can_manage_tasks,
    can_pick_reserve_manager,
    resolve_reserve_form_manager_id,
    can_sale_from_reserve,
    data_owner_manager_id,
    form_owner_manager_id,
    reserve_owner_manager_id,
    reserves_scope_manager_id,
    show_reserves_manager_column,
)
from web.sales_urls import analytics_sales_return_url
from web.services.analytics import AnalyticsService
from web.services.clients_filter import (
    ClientFilters,
    SalesFilters,
    build_client_filter_options,
    build_sales_filter_options,
    sales_filters_active,
    sales_filters_to_client,
)
from web.services.dashboard import DashboardService
from web.services.sales_plans import SalesPlanProgress, SalesPlanService
from web.services.stand_transfer import StandTransferService
from web.services.tasks_board import (
    TASK_STATUS_ACTIVE,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_OVERDUE,
    build_tasks_board,
)
from web.sales_matrix_pdf import build_sales_matrix_pdf
from web.stands_pdf import build_stands_clients_pdf
from web.ttl_cache import get_or_load, invalidate_sales_analytics_cache
from web.utils import (
    client_stands_map_json,
    parse_manager_task_kind_filter,
    tasks_page_query,
    uk_month_name,
    warehouse_stands_map_json,
)


_STANDS_DETAIL_BUCKETS = frozenset({
    "manager_total",
    "manager_stand",
    "city_total",
    "city_stand",
    "oblast_total",
    "oblast_stand",
})


async def _load_stands_clients_detail(request, user, service: AnalyticsService):
    bucket = (query_str(request, "bucket") or "").strip()
    if bucket not in _STANDS_DETAIL_BUCKETS:
        raise HTTPException(status_code=400, detail="Invalid bucket")
    manager_id = scoped_manager_filter(user, query_int(request, "manager_id"))
    filters = ClientFilters(
        manager_id=manager_id,
        region_id=query_int(request, "region_id"),
        city=query_str(request, "city"),
        stand_id=query_int(request, "stand_id"),
    )
    city_detail = query_str(request, "city_detail") or None
    detail_kwargs = {
        "manager": query_str(request, "manager") or None,
        "stand": query_str(request, "stand") or None,
        "city": city_detail,
        "oblast": query_str(request, "oblast") or None,
    }
    rows = await service.stands_clients_detail(filters, bucket=bucket, **detail_kwargs)
    title = service.stands_detail_title(bucket, **detail_kwargs)
    return rows, title


def _resolve_sales_period(
    period_kind: str,
    year: int,
    month: int,
    quarter: int,
):
    if period_kind == "quarter":
        return quarter_range(year, quarter)
    if period_kind == "year":
        return year_range(year)
    return month_range(year, month)


def _sales_analytics_cache_key(
    *,
    period_kind: str,
    year: int,
    month: int,
    quarter: int,
    sales_filters: SalesFilters,
) -> str:
    return ":".join(
        [
            "sales-bundle",
            period_kind,
            str(year),
            str(month),
            str(quarter),
            str(sales_filters.manager_id or ""),
            str(sales_filters.region_id or ""),
            sales_filters.city or "",
            str(sales_filters.stand_id or ""),
            str(sales_filters.brand_id or ""),
        ]
    )


async def _load_sales_analytics_bundle(
    service: AnalyticsService,
    plan_service: SalesPlanService,
    *,
    period,
    sales_filters: SalesFilters,
    period_kind: str,
    year: int,
    month: int,
    quarter: int,
    include_plans: bool,
):
    cache_key = _sales_analytics_cache_key(
        period_kind=period_kind,
        year=year,
        month=month,
        quarter=quarter,
        sales_filters=sales_filters,
    )

    async def loader():
        return {
            "sales_by_manager": await service.sales_by_manager(period, sales_filters),
            "sales_by_brand": await service.sales_by_brand(period, sales_filters),
            "sales_by_client": await service.sales_by_client(period, sales_filters),
            "sales_by_oblast": await service.sales_by_oblast(period, sales_filters),
            "brands_by_city_rows": await service.brands_by_city_split(
                period, sales_filters
            ),
            "brands_by_oblast_rows": await service.brands_by_oblast_split(
                period, sales_filters
            ),
            "total_sales": await service.sales_total(period, sales_filters),
            "sales_ledger": await service.sales_ledger(period, sales_filters),
            "sales_plan_progress": (
                await plan_service.progress_for_all_managers(year=year, month=month)
                if include_plans
                else []
            ),
        }

    return await get_or_load(cache_key, loader)


def _analytics_partial_query(request: Request) -> str:
    return str(request.url.query)


def register_panel_routes(
    app,
    *,
    templates,
    get_session,
    require_auth,
    dashboard_service,
    settings: Settings,
):
    def analytics_service(session: AsyncSession = Depends(get_session)) -> AnalyticsService:
        return AnalyticsService(session)

    def sales_plan_service(session: AsyncSession = Depends(get_session)) -> SalesPlanService:
        return SalesPlanService(session)

    @app.get("/analytics", response_class=HTMLResponse)
    async def analytics_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: AnalyticsService = Depends(analytics_service),
        dashboard: DashboardService = Depends(dashboard_service),
        plan_service: SalesPlanService = Depends(sales_plan_service),
        _auth: Response | None = Depends(require_auth),
        section: str = "sales",
        period_kind: str = "month",
        year: int | None = None,
        month: int | None = None,
        quarter: int | None = None,
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "analytics")
        manager_id = scoped_manager_filter(user, query_int(request, "manager_id"))

        today = date_cls.today()
        year = year or today.year
        month = month or today.month
        quarter = quarter or ((month - 1) // 3 + 1)

        managers = await service.list_managers()
        ctx = page_ctx(
            user,
            active_nav="analytics",
            section=section,
            analytics_section=section,
            managers=managers,
            selected_manager_id=manager_id,
        )

        if section == "sales":
            region_id = query_int(request, "region_id")
            city = query_str(request, "city")
            stand_id = query_int(request, "stand_id")
            brand_id = query_int(request, "brand_id")
            sales_filters = SalesFilters(
                manager_id=manager_id,
                region_id=region_id,
                city=city,
                stand_id=stand_id,
                brand_id=brand_id,
            )
            filter_clients_pool = await dashboard.list_clients_for_filters(
                manager_id=manager_id,
            )
            stands = await dashboard.list_active_stands()
            brands = await dashboard.list_active_brands()
            filter_opts = build_sales_filter_options(
                filter_clients_pool,
                stands,
                brands,
                manager_id=manager_id,
                region_id=region_id,
            )
            period = _resolve_sales_period(period_kind, year, month, quarter)
            bundle = await _load_sales_analytics_bundle(
                service,
                plan_service,
                period=period,
                sales_filters=sales_filters,
                period_kind=period_kind,
                year=year,
                month=month,
                quarter=quarter,
                include_plans=period_kind == "month" and can_filter_managers(user),
            )
            partial_q = _analytics_partial_query(request)

            ctx.update(
                period_kind=period_kind,
                year=year,
                month=month,
                quarter=quarter,
                period_label=period.label,
                period_kind_label={
                    "month": "місяць",
                    "quarter": "квартал",
                    "year": "рік",
                }.get(period_kind, period_kind),
                sales_by_manager=bundle["sales_by_manager"],
                sales_by_brand=bundle["sales_by_brand"],
                sales_by_client=bundle["sales_by_client"],
                sales_by_oblast=bundle["sales_by_oblast"],
                brands_by_city_rows=bundle["brands_by_city_rows"],
                brands_by_oblast_rows=bundle["brands_by_oblast_rows"],
                total_sales=bundle["total_sales"],
                sales_ledger=bundle["sales_ledger"],
                sales_plan_progress=bundle["sales_plan_progress"],
                filter_regions=filter_opts.regions,
                filter_cities=filter_opts.cities,
                filter_stands=filter_opts.stands,
                filter_brands=filter_opts.brands,
                selected_region_id=region_id,
                selected_city=city,
                selected_stand_id=stand_id,
                selected_brand_id=brand_id,
                sales_has_filters=sales_filters_active(sales_filters),
                sales_matrix_partial_url=f"/analytics/partials/sales-matrix?{partial_q}",
                sales_matrix_pdf_url=f"/analytics/sales-matrix.pdf?{partial_q}",
                inactive_stands_partial_url=f"/analytics/partials/inactive-stands?{partial_q}",
                sales_return_url=analytics_sales_return_url(
                    dict(request.query_params)
                ),
                can_manage_sale=can_manage_sale,
                sale_default_sold_at=period.start.isoformat(),
                sales_plan_month_label=uk_month_name(month),
            )
            return templates.TemplateResponse(request, "analytics.html", ctx)

        if section == "compare":
            compare_kind = query_str(request, "compare_kind", default="month") or "month"
            region_id = query_int(request, "region_id")
            city = query_str(request, "city")
            stand_id = query_int(request, "stand_id")
            brand_id = query_int(request, "brand_id")
            sales_filters = SalesFilters(
                manager_id=manager_id,
                region_id=region_id,
                city=city,
                stand_id=stand_id,
                brand_id=brand_id,
            )
            prev_period = prev_month_range(today.year, today.month)
            default_b_quarter = (prev_period.start.month - 1) // 3 + 1

            a_year = query_int(request, "a_year", default=today.year) or today.year
            a_month = query_int(request, "a_month", default=today.month) or today.month
            a_quarter = query_int(request, "a_quarter", default=quarter) or quarter
            b_year = (
                query_int(request, "b_year", default=prev_period.start.year)
                or prev_period.start.year
            )
            b_month = (
                query_int(request, "b_month", default=prev_period.start.month)
                or prev_period.start.month
            )
            b_quarter = (
                query_int(request, "b_quarter", default=default_b_quarter)
                or default_b_quarter
            )

            if compare_kind == "year":
                default_b_year = today.year - 1
                a_year = query_int(request, "a_year", default=today.year) or today.year
                b_year = query_int(request, "b_year", default=default_b_year) or default_b_year
                report_range = year_range(a_year)
                base_range = year_range(b_year)
            elif compare_kind == "quarter":
                report_range = quarter_range(a_year, a_quarter)
                base_range = quarter_range(b_year, b_quarter)
            else:
                report_range = month_range(a_year, a_month)
                base_range = month_range(b_year, b_month)

            all_clients = await dashboard.list_clients()
            stands = await dashboard.list_active_stands()
            brands = await dashboard.list_active_brands()
            filter_opts = build_sales_filter_options(
                all_clients,
                stands,
                brands,
                manager_id=manager_id,
                region_id=region_id,
            )

            ctx.update(
                compare_kind=compare_kind,
                a_year=a_year,
                a_month=a_month,
                a_quarter=a_quarter,
                b_year=b_year,
                b_month=b_month,
                b_quarter=b_quarter,
                report_label=report_range.label,
                base_label=base_range.label,
                compare_managers=await service.compare_managers_table(
                    report_range, base_range, sales_filters
                ),
                compare_kpis=await service.compare_kpis(
                    report_range, base_range, sales_filters
                ),
                compare_brands=await service.compare_brands(
                    report_range, base_range, sales_filters
                ),
                compare_clients=await service.compare_clients(
                    report_range, base_range, sales_filters
                ),
                filter_regions=filter_opts.regions,
                filter_cities=filter_opts.cities,
                filter_stands=filter_opts.stands,
                filter_brands=filter_opts.brands,
                selected_region_id=region_id,
                selected_city=city,
                selected_stand_id=stand_id,
                selected_brand_id=brand_id,
                sales_has_filters=sales_filters_active(sales_filters),
            )
            return templates.TemplateResponse(request, "analytics_compare.html", ctx)

        if section == "stands":
            region_id = query_int(request, "region_id")
            city = query_str(request, "city")
            stand_id = query_int(request, "stand_id")
            filters = ClientFilters(
                manager_id=manager_id,
                region_id=region_id,
                city=city,
                stand_id=stand_id,
            )
            all_clients = await dashboard.list_clients()
            stands = await dashboard.list_active_stands()
            opts = build_client_filter_options(
                all_clients,
                stands,
                manager_id=manager_id,
                region_id=region_id,
            )
            owner = data_owner_manager_id(user) or user.id
            if can_filter_managers(user) and manager_id is None:
                move_clients = all_clients
            elif manager_id is not None:
                move_clients = [c for c in all_clients if c.manager_id == manager_id]
            else:
                move_clients = [c for c in all_clients if c.manager_id == owner]

            scope_name = "всі"
            if manager_id is not None:
                picked = next((m for m in managers if m.id == manager_id), None)
                if picked is not None:
                    scope_name = picked.name.split()[0]
            elif not can_filter_managers(user):
                scope_name = user.name.split()[0]

            wh_owner = manager_id or owner
            wh_svc = StandTransferService(session)
            wh_stock = await wh_svc.list_warehouse_stock(wh_owner)

            ctx.update(
                stands_scope_name=scope_name,
                warehouse_manager_id=wh_owner,
                warehouse_stands_json=warehouse_stands_map_json(wh_stock),
                stands_total_by_manager=await service.stands_total_by_manager(filters),
                stands_by_manager_stand=await service.stands_by_manager_and_stand(
                    filters
                ),
                stands_totals_city=await service.stands_totals_by_city(filters),
                stands_by_city=await service.stands_by_city_and_stand(filters),
                stands_totals_oblast=await service.stands_totals_by_oblast(filters),
                stands_by_oblast=await service.stands_by_oblast_and_stand(filters),
                filter_regions=opts.regions,
                filter_cities=opts.cities,
                filter_stands=opts.stands,
                selected_region_id=region_id,
                selected_city=city,
                selected_stand_id=stand_id,
                stands_has_filters=any(
                    [manager_id, region_id, city, stand_id is not None]
                ),
                move_clients=move_clients,
                client_stands_json=client_stands_map_json(move_clients),
            )
            return templates.TemplateResponse(request, "analytics.html", ctx)

        return RedirectResponse("/analytics?section=sales", status_code=303)

    @app.get("/analytics/partials/sales-matrix", response_class=HTMLResponse)
    async def analytics_sales_matrix_partial(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: AnalyticsService = Depends(analytics_service),
        _auth: Response | None = Depends(require_auth),
        period_kind: str = "month",
        year: int | None = None,
        month: int | None = None,
        quarter: int | None = None,
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "analytics")
        manager_id = scoped_manager_filter(user, query_int(request, "manager_id"))
        today = date_cls.today()
        year = year or today.year
        month = month or today.month
        quarter = quarter or ((month - 1) // 3 + 1)
        sales_filters = SalesFilters(
            manager_id=manager_id,
            region_id=query_int(request, "region_id"),
            city=query_str(request, "city"),
            stand_id=query_int(request, "stand_id"),
            brand_id=query_int(request, "brand_id"),
        )
        period = _resolve_sales_period(period_kind, year, month, quarter)
        sales_matrix_cols, sales_matrix_rows = await service.sales_matrix_from_stands(
            period, sales_filters
        )
        return templates.TemplateResponse(
            request,
            "partials/sales_matrix_block.html",
            {
                "period_label": period.label,
                "sales_matrix_cols": sales_matrix_cols,
                "sales_matrix_rows": sales_matrix_rows,
                "sales_matrix_pdf_url": f"/analytics/sales-matrix.pdf?{request.url.query}",
            },
        )

    @app.get("/analytics/sales-matrix.pdf")
    async def analytics_sales_matrix_pdf(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: AnalyticsService = Depends(analytics_service),
        _auth: Response | None = Depends(require_auth),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "analytics")
        manager_id = scoped_manager_filter(user, query_int(request, "manager_id"))
        today = date_cls.today()
        year = query_int(request, "year", default=today.year) or today.year
        month = query_int(request, "month", default=today.month) or today.month
        quarter = query_int(request, "quarter") or ((month - 1) // 3 + 1)
        period_kind = query_str(request, "period_kind", default="month") or "month"
        sales_filters = SalesFilters(
            manager_id=manager_id,
            region_id=query_int(request, "region_id"),
            city=query_str(request, "city"),
            stand_id=query_int(request, "stand_id"),
            brand_id=query_int(request, "brand_id"),
        )
        period = _resolve_sales_period(period_kind, year, month, quarter)
        sales_matrix_cols, sales_matrix_rows = await service.sales_matrix_from_stands(
            period, sales_filters
        )
        title = f"Продажі (матриця) — {period.label}"
        try:
            pdf_bytes = build_sales_matrix_pdf(
                title=title,
                columns=sales_matrix_cols,
                rows=sales_matrix_rows,
                generated_at=datetime.now(ZoneInfo("Europe/Kyiv")),
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="sales-matrix.pdf"'
            },
        )

    @app.get("/analytics/partials/inactive-stands", response_class=HTMLResponse)
    async def analytics_inactive_stands_partial(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: AnalyticsService = Depends(analytics_service),
        _auth: Response | None = Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "analytics")
        manager_id = scoped_manager_filter(user, query_int(request, "manager_id"))
        sales_filters = SalesFilters(
            manager_id=manager_id,
            region_id=query_int(request, "region_id"),
            city=query_str(request, "city"),
            stand_id=query_int(request, "stand_id"),
        )
        inactive_filters = sales_filters_to_client(sales_filters)
        inactive_3, inactive_6 = await service.stands_not_worked(inactive_filters)
        stands_not_worked_rows = sorted(
            [*inactive_3, *inactive_6],
            key=lambda r: (
                r.period_label,
                r.stand_name.casefold(),
                r.client_label.casefold(),
            ),
        )
        return templates.TemplateResponse(
            request,
            "partials/inactive_stands_block.html",
            page_ctx(
                user,
                stands_not_worked_rows=stands_not_worked_rows,
                stands_not_worked_count_3=len(inactive_3),
                stands_not_worked_count_6=len(inactive_6),
            ),
        )

    @app.get("/analytics/partials/stands-clients", response_class=HTMLResponse)
    async def analytics_stands_clients_partial(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: AnalyticsService = Depends(analytics_service),
        _auth: Response | None = Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "analytics")
        rows, title = await _load_stands_clients_detail(request, user, service)
        return templates.TemplateResponse(
            request,
            "partials/stands_clients_detail.html",
            page_ctx(
                user,
                rows=rows,
                detail_title=title,
            ),
        )

    @app.get("/analytics/stands-clients.pdf")
    async def analytics_stands_clients_pdf(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: AnalyticsService = Depends(analytics_service),
        _auth: Response | None = Depends(require_auth),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "analytics")
        rows, title = await _load_stands_clients_detail(request, user, service)
        try:
            pdf_bytes = build_stands_clients_pdf(
                title=title,
                rows=rows,
                show_manager=can_filter_managers(user),
                generated_at=datetime.now(ZoneInfo("Europe/Kyiv")),
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="stands-clients.pdf"'
            },
        )

    @app.get("/sales/{sale_id}/edit", response_class=HTMLResponse)
    async def sale_edit_page(
        request: Request,
        sale_id: int,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "analytics")
        await assert_sale_manage_access(session, user, sale_id)
        sale = await SaleRepository(session).get_by_id(sale_id)
        if sale is None:
            raise HTTPException(status_code=404, detail="Продаж не знайдено")
        clients = [
            c
            for c in await dashboard.list_clients()
            if c.manager_id == sale.manager_id
        ]
        clients.sort(key=lambda c: c.name.casefold())
        brands = await dashboard.list_active_brands()
        return_url = request.query_params.get("return_url") or "/analytics?section=sales"
        return templates.TemplateResponse(
            request,
            "sale_form.html",
            page_ctx(
                user,
                active_nav="analytics",
                analytics_section="sales",
                sale=sale,
                clients=clients,
                brands=brands,
                return_url=return_url,
            ),
        )

    @app.post("/sales/{sale_id}/edit")
    async def sale_edit_save(
        request: Request,
        sale_id: int,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
        client_id: int = Form(...),
        brand_id: int = Form(...),
        quantity: str = Form(...),
        sold_at: str = Form(...),
        comment: str = Form(""),
        return_url: str = Form("/analytics?section=sales"),
    ) -> RedirectResponse:
        user = await load_web_user(request, session)
        require_nav(user, "analytics")
        manager_id = await assert_sale_manage_access(session, user, sale_id)
        sale = await SaleRepository(session).get_by_id(sale_id)
        if sale is None:
            raise HTTPException(status_code=404, detail="Продаж не знайдено")

        client = await dashboard.get_client(client_id)
        if client is None or client.manager_id != manager_id:
            raise HTTPException(status_code=400, detail="Невірна торгова точка")

        from bot.utils.client_brands import brands_for_client, sale_is_from_swatch

        all_brands = await dashboard.list_active_brands()
        allowed_ids = {b.id for b in brands_for_client(client, all_brands)}
        if brand_id not in allowed_ids:
            raise HTTPException(status_code=400, detail="Невірна торгова марка")
        from_swatch = sale_is_from_swatch(client, brand_id, all_brands)

        try:
            qty = Decimal(quantity.replace(",", ".").strip())
        except InvalidOperation as exc:
            raise HTTPException(status_code=400, detail="Невірна кількість") from exc
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Кількість має бути більше 0")

        try:
            sale_date = date_cls.fromisoformat(sold_at.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Невірна дата продажу") from exc

        await SaleRepository(session).update(
            sale_id,
            client_id=client_id,
            brand_id=brand_id,
            quantity=qty,
            sold_at=sale_date,
            comment=comment.strip() or None,
            from_swatch=from_swatch,
        )
        await session.commit()
        invalidate_sales_analytics_cache()
        safe_return = return_url if return_url.startswith("/analytics") else "/analytics?section=sales"
        return RedirectResponse(safe_return, status_code=303)

    @app.post("/sales/{sale_id}/delete")
    async def sale_delete(
        request: Request,
        sale_id: int,
        session: AsyncSession = Depends(get_session),
        _auth: Response | None = Depends(require_auth),
        return_url: str = Form("/analytics?section=sales"),
    ) -> RedirectResponse:
        user = await load_web_user(request, session)
        require_nav(user, "analytics")
        await assert_sale_manage_access(session, user, sale_id)
        deleted = await SaleRepository(session).delete(sale_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Продаж не знайдено")
        await session.commit()
        invalidate_sales_analytics_cache()
        safe_return = return_url if return_url.startswith("/analytics") else "/analytics?section=sales"
        return RedirectResponse(safe_return, status_code=303)

    @app.post("/sales/new")
    async def sale_create(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth: Response | None = Depends(require_auth),
        client_id: int = Form(...),
        brand_id: int = Form(...),
        quantity: str = Form(...),
        sold_at: str = Form(...),
        comment: str = Form(""),
        manager_id: str = Form(""),
        return_url: str = Form("/analytics?section=sales"),
    ) -> RedirectResponse:
        user = await load_web_user(request, session)
        require_nav(user, "analytics")
        require_sale_create(user)

        requested_manager_id = (
            int(manager_id.strip())
            if can_pick_reserve_manager(user) and manager_id.strip().isdigit()
            else None
        )
        if can_pick_reserve_manager(user) and requested_manager_id is None:
            raise HTTPException(status_code=400, detail="Оберіть менеджера")
        try:
            target_manager_id = resolve_reserve_form_manager_id(
                user, requested_manager_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Оберіть менеджера") from exc

        client = await ClientRepository(session).get_by_id(client_id)
        if client is None or client.manager_id != target_manager_id:
            raise HTTPException(status_code=400, detail="Невірна торгова точка")

        from bot.utils.client_brands import brands_for_client, sale_is_from_swatch
        from database.repositories.brand import BrandRepository

        all_brands = await BrandRepository(session).list_active()
        allowed_ids = {b.id for b in brands_for_client(client, all_brands)}
        if brand_id not in allowed_ids:
            raise HTTPException(status_code=400, detail="Невірна торгова марка")
        from_swatch = sale_is_from_swatch(client, brand_id, all_brands)

        try:
            qty = Decimal(quantity.replace(",", ".").strip())
        except InvalidOperation as exc:
            raise HTTPException(status_code=400, detail="Невірна кількість") from exc
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Кількість має бути більше 0")

        try:
            sale_date = date_cls.fromisoformat(sold_at.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Невірна дата продажу") from exc

        await SaleRepository(session).create(
            manager_id=target_manager_id,
            client_id=client_id,
            brand_id=brand_id,
            quantity=qty,
            sold_at=sale_date,
            comment=comment.strip() or None,
            from_swatch=from_swatch,
        )
        await session.commit()
        invalidate_sales_analytics_cache()
        safe_return = return_url if return_url.startswith("/analytics") else "/analytics?section=sales"
        return RedirectResponse(safe_return, status_code=303)

    def _reserves_redirect(return_manager_id: str = "") -> str:
        if return_manager_id.strip().isdigit():
            return f"/reserves?manager_id={return_manager_id.strip()}"
        return "/reserves"

    @app.get("/reserves", response_class=HTMLResponse)
    async def reserves_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
        page: int = 1,
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "reserves")
        manager_id = reserves_scope_manager_id(
            user, query_int(request, "manager_id")
        )
        managers = (
            await service.list_managers()
            if can_filter_reserves_managers(user)
            else []
        )

        now = datetime.now(timezone.utc)
        per_page = DashboardService.RESERVES_PER_PAGE
        filters = list(ReserveRepository.list_visible_filter(now))
        if manager_id is not None:
            filters.append(Reserve.manager_id == manager_id)

        total_result = await session.execute(
            select(func.count()).select_from(Reserve).where(*filters)
        )
        total = int(total_result.scalar_one())
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page

        stmt = (
            select(Reserve)
            .where(*filters)
            .options(
                selectinload(Reserve.manager),
                selectinload(Reserve.created_by),
                selectinload(Reserve.client),
                selectinload(Reserve.region),
            )
            .order_by(Reserve.sold_at.asc().nullsfirst(), Reserve.expires_at.asc())
            .limit(per_page)
            .offset(offset)
        )
        result = await session.execute(stmt)
        reserves = list(result.scalars().all())

        return templates.TemplateResponse(
            request,
            "reserves.html",
            page_ctx(
                user,
                active_nav="reserves",
                reserves=reserves,
                managers=managers,
                selected_manager_id=manager_id,
                show_reserves_manager=show_reserves_manager_column(user),
                can_filter_reserves=can_filter_reserves_managers(user),
                page=page,
                total_pages=total_pages,
                reserves_total=total,
            ),
        )

    @app.post("/reserves/new")
    async def reserves_create(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth: Response | None = Depends(require_auth),
        region_id: int = Form(...),
        client_id: int = Form(...),
        material: str = Form(...),
        quantity: str = Form(...),
        manager_id: str = Form(""),
        return_manager_id: str = Form(""),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "reserves")
        require_reserve_create(user)

        requested_manager_id = (
            int(manager_id.strip())
            if can_pick_reserve_manager(user) and manager_id.strip().isdigit()
            else None
        )
        if can_pick_reserve_manager(user) and requested_manager_id is None:
            raise HTTPException(status_code=400, detail="Оберіть менеджера")

        try:
            target_manager_id = resolve_reserve_form_manager_id(
                user, requested_manager_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Оберіть менеджера") from exc

        if can_pick_reserve_manager(user):
            allowed = {
                u.id
                for u in filter_regional_managers(
                    await UserRepository(session).list_all()
                )
            }
            if target_manager_id not in allowed:
                raise HTTPException(status_code=400, detail="Невірний менеджер")

        region = await RegionRepository(session).get_by_id(region_id)
        if region is None or region.manager_id != target_manager_id:
            raise HTTPException(status_code=400, detail="Невірна область")

        client = await ClientRepository(session).get_by_id(client_id)
        if (
            client is None
            or client.manager_id != target_manager_id
            or client.region_id != region_id
        ):
            raise HTTPException(status_code=400, detail="Невірний клієнт")

        material_text = material.strip()
        if not material_text:
            raise HTTPException(status_code=400, detail="Вкажіть матеріал")

        try:
            qty = Decimal(quantity.replace(",", ".").strip())
        except InvalidOperation as exc:
            raise HTTPException(status_code=400, detail="Невірна кількість") from exc
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Кількість має бути більше 0")

        repo = ReserveRepository(session)
        reserve = await repo.create(
            manager_id=target_manager_id,
            region_id=region_id,
            client_id=client_id,
            material=material_text,
            quantity=qty,
            created_by_id=user.id,
        )
        creator = await session.get(User, user.id)
        await session.commit()

        if settings.bot_token.strip():
            users = await UserRepository(session).list_all()
            await broadcast_new_reserve(
                bot_token=settings.bot_token,
                users=users,
                reserve_id=reserve.id,
                manager_name=creator.name if creator and creator.name else "Менеджер",
                client_name=client.name,
                region_name=region.name,
                material=reserve.material,
                quantity=qty,
                expires_at=reserve.expires_at,
            )

        return RedirectResponse(_reserves_redirect(return_manager_id), status_code=303)

    @app.post("/reserves/extend")
    async def reserves_extend(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth: Response | None = Depends(require_auth),
        reserve_id: int = Form(...),
        return_manager_id: str = Form(""),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "reserves")
        repo = ReserveRepository(session)
        reserve = await repo.get_by_id(reserve_id)
        if reserve is None:
            raise HTTPException(status_code=404, detail="Резерв не знайдено")
        assert_reserve_manage_access(user, reserve)
        if reserve.sold_at is not None:
            raise HTTPException(status_code=400, detail="Резерв уже продано")
        await repo.extend(reserve_id)
        await session.commit()
        return RedirectResponse(_reserves_redirect(return_manager_id), status_code=303)

    @app.post("/reserves/cancel")
    async def reserves_cancel(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth: Response | None = Depends(require_auth),
        reserve_id: int = Form(...),
        return_manager_id: str = Form(""),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "reserves")
        repo = ReserveRepository(session)
        reserve = await repo.get_by_id(reserve_id)
        if reserve is None:
            raise HTTPException(status_code=404, detail="Резерв не знайдено")
        assert_reserve_manage_access(user, reserve)
        if reserve.sold_at is not None:
            raise HTTPException(status_code=400, detail="Резерв уже продано")
        await repo.cancel(reserve_id)
        await session.commit()
        return RedirectResponse(_reserves_redirect(return_manager_id), status_code=303)

    @app.post("/reserves/sale")
    async def reserves_sale(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth: Response | None = Depends(require_auth),
        reserve_id: int = Form(...),
        brand_id: int = Form(...),
        quantity: str = Form(...),
        return_manager_id: str = Form(""),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "reserves")

        repo = ReserveRepository(session)
        reserve = await repo.get_by_id(reserve_id)
        if reserve is None or reserve.cancelled_at is not None:
            raise HTTPException(status_code=404, detail="Резерв не знайдено")
        if reserve.sold_at is not None:
            raise HTTPException(status_code=400, detail="Резерв уже продано")
        if not can_sale_from_reserve(user, manager_id=reserve.manager_id):
            raise HTTPException(status_code=403, detail="Forbidden")

        client = await ClientRepository(session).get_by_id(reserve.client_id)
        if client is None:
            raise HTTPException(status_code=400, detail="Клієнта не знайдено")

        from bot.utils.client_brands import brands_for_client, sale_is_from_swatch
        from database.repositories.brand import BrandRepository

        all_brands = await BrandRepository(session).list_active()
        allowed_ids = {b.id for b in brands_for_client(client, all_brands)}
        if brand_id not in allowed_ids:
            raise HTTPException(status_code=400, detail="Невірна торгова марка")
        from_swatch = sale_is_from_swatch(client, brand_id, all_brands)

        try:
            qty = Decimal(quantity.replace(",", ".").strip())
        except InvalidOperation as exc:
            raise HTTPException(status_code=400, detail="Невірна кількість") from exc
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Кількість має бути більше 0")

        today = date_cls.today()
        sold_at = date_cls(today.year, today.month, 1)
        comment = f"Продаж з резерву #{reserve.id}"

        await SaleRepository(session).create(
            manager_id=user.id,
            client_id=reserve.client_id,
            brand_id=brand_id,
            quantity=qty,
            sold_at=sold_at,
            comment=comment,
            from_swatch=from_swatch,
        )
        if await repo.mark_sold(reserve_id) is None:
            raise HTTPException(status_code=400, detail="Не вдалося закрити резерв")
        await session.commit()
        invalidate_sales_analytics_cache()
        return RedirectResponse(_reserves_redirect(return_manager_id), status_code=303)

    @app.get("/tasks", response_class=HTMLResponse)
    async def tasks_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        plan_service: SalesPlanService = Depends(sales_plan_service),
        _auth: Response | None = Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "tasks")

        today = date_cls.today()
        plan_year = query_int(request, "plan_year", default=today.year) or today.year
        plan_month = query_int(request, "plan_month", default=today.month) or today.month
        if plan_month < 1 or plan_month > 12:
            plan_month = today.month

        managers = await service.list_managers()
        filter_manager_id = scoped_manager_filter(
            user, query_int(request, "manager_id")
        )
        status_filter = query_str(request, "status") or TASK_STATUS_ACTIVE
        if status_filter not in (
            TASK_STATUS_ACTIVE,
            TASK_STATUS_OVERDUE,
            TASK_STATUS_COMPLETED,
        ):
            status_filter = TASK_STATUS_ACTIVE
        kind_filter = parse_manager_task_kind_filter(query_str(request, "kind"))
        show_archive = request.query_params.get("show_completed", "").strip() in (
            "1",
            "true",
            "yes",
            "on",
        )

        stmt = (
            select(Task)
            .options(selectinload(Task.assignee), selectinload(Task.created_by))
            .order_by(
                Task.deleted_at.asc().nullslast(),
                Task.completed_at.asc().nullslast(),
                Task.deadline.asc().nullslast(),
                Task.weekday.asc().nullslast(),
                Task.created_at.desc(),
            )
        )
        if filter_manager_id is not None:
            stmt = stmt.where(Task.assignee_id == filter_manager_id)
        if kind_filter:
            stmt = stmt.where(Task.kind == kind_filter)
        if status_filter == TASK_STATUS_COMPLETED:
            if show_archive:
                stmt = stmt.where(
                    (Task.completed_at.is_not(None)) | (Task.deleted_at.is_not(None))
                )
            else:
                stmt = stmt.where(
                    Task.completed_at.is_not(None),
                    Task.deleted_at.is_(None),
                )
        elif status_filter == TASK_STATUS_OVERDUE:
            stmt = stmt.where(
                Task.deleted_at.is_(None),
                Task.completed_at.is_(None),
                Task.deadline < today,
            )
        else:
            stmt = stmt.where(
                Task.deleted_at.is_(None),
                Task.completed_at.is_(None),
            )
        stmt = stmt.limit(500)
        result = await session.execute(stmt)
        tasks = list(result.scalars().all())

        board_stats, manager_sections = build_tasks_board(
            tasks,
            managers,
            today=date_cls.today(),
            manager_id=filter_manager_id,
            show_completed=show_archive,
            status_filter=status_filter,
            kind_filter=kind_filter,
        )

        sales_plan_progress = None
        if user.is_manager:
            sales_plan_progress = await plan_service.progress_for_manager(
                user.id,
                user.name,
                year=today.year,
                month=today.month,
            )
            plan_month_label_for_ring = uk_month_name(today.month)
        else:
            plan_month_label_for_ring = uk_month_name(plan_month)

        sales_plan_rows = []
        if can_manage_sales_plans(user):
            sales_plan_rows = await plan_service.progress_for_all_managers(
                year=plan_year,
                month=plan_month,
            )

        return templates.TemplateResponse(
            request,
            "tasks.html",
            page_ctx(
                user,
                active_nav="tasks",
                managers=managers,
                board_stats=board_stats,
                manager_sections=manager_sections,
                selected_manager_id=filter_manager_id,
                selected_kind=kind_filter,
                status_filter=status_filter,
                show_completed=show_archive,
                sales_plan_progress=sales_plan_progress,
                sales_plan_rows=sales_plan_rows,
                plan_year=plan_year,
                plan_month=plan_month,
                plan_month_label=plan_month_label_for_ring if user.is_manager else uk_month_name(plan_month),
                plan_year_display=today.year if user.is_manager else plan_year,
            ),
        )

    @app.post("/tasks/sales-plans")
    async def tasks_sales_plans_save(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth: Response | None = Depends(require_auth),
        plan_year: int = Form(...),
        plan_month: int = Form(...),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "tasks")
        if not can_manage_sales_plans(user):
            raise HTTPException(status_code=403, detail="Forbidden")

        if plan_month < 1 or plan_month > 12:
            raise HTTPException(status_code=400, detail="Невірний місяць")

        form = await request.form()
        managers = filter_regional_managers(
            await UserRepository(session).list_all()
        )
        allowed_ids = {m.id for m in managers}
        values: dict[int, Decimal] = {}
        for m in managers:
            raw = form.get(f"plan_{m.id}", "")
            if not raw or not str(raw).strip():
                continue
            try:
                qty = Decimal(str(raw).strip().replace(",", "."))
            except InvalidOperation as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Невірний план для {m.name}",
                ) from exc
            if qty <= 0:
                continue
            if m.id not in allowed_ids:
                continue
            values[m.id] = qty

        plan_service = SalesPlanService(session)
        await plan_service.save_plans(
            year=plan_year,
            month=plan_month,
            values=values,
            created_by_id=user.id,
        )
        await session.commit()
        return RedirectResponse(
            f"/tasks?plan_year={plan_year}&plan_month={plan_month}",
            status_code=303,
        )

    @app.post("/tasks")
    async def tasks_create(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
        assignee_id: int = Form(...),
        title: str = Form(...),
        deadline: str = Form(""),
        weekday: str = Form(""),
        kind: str = Form(ManagerTaskKind.GENERAL.value),
        comment: str = Form(""),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "tasks")
        require_task_create(user)

        effective_assignee_id = assignee_id if can_manage_tasks(user) else user.id

        dl = None
        if deadline.strip():
            dl = date_cls.fromisoformat(deadline.strip())
        wd = int(weekday) if weekday.strip() else None

        creator = await session.get(User, user.id)
        task = Task(
            assignee_id=effective_assignee_id,
            created_by_id=user.id,
            title=title.strip(),
            comment=comment.strip() or None,
            deadline=dl,
            weekday=wd,
            kind=normalize_manager_task_kind(kind),
        )
        session.add(task)
        await session.flush()
        assignee = await session.get(User, effective_assignee_id)
        await session.commit()
        if assignee and creator and settings.bot_token.strip():
            await notify_task_assigned(
                bot_token=settings.bot_token,
                task=task,
                assignee=assignee,
                creator=creator,
            )
        return RedirectResponse("/tasks", status_code=303)

    @app.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
    async def tasks_edit_page(
        request: Request,
        task_id: int,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "tasks")
        result = await session.execute(
            select(Task).options(selectinload(Task.assignee)).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        assert_task_manage_access(user, task)
        return templates.TemplateResponse(
            request,
            "task_edit.html",
            page_ctx(
                user,
                active_nav="tasks",
                task=task,
                managers=await service.list_managers(),
            ),
        )

    @app.post("/tasks/{task_id}/edit")
    async def tasks_edit_save(
        request: Request,
        task_id: int,
        session: AsyncSession = Depends(get_session),
        _auth: Response | None = Depends(require_auth),
        assignee_id: int = Form(...),
        title: str = Form(...),
        deadline: str = Form(""),
        weekday: str = Form(""),
        kind: str = Form(ManagerTaskKind.GENERAL.value),
        comment: str = Form(""),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "tasks")

        task = await session.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        assert_task_manage_access(user, task)

        dl = None
        if deadline.strip():
            dl = date_cls.fromisoformat(deadline.strip())
        wd = int(weekday) if weekday.strip() else None

        task.assignee_id = assignee_id if can_manage_tasks(user) else user.id
        task.title = title.strip()
        task.deadline = dl
        task.weekday = wd
        task.kind = normalize_manager_task_kind(kind)
        task.comment = comment.strip() or None
        await session.commit()
        return RedirectResponse("/tasks", status_code=303)

    @app.post("/tasks/complete")
    async def tasks_complete(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth: Response | None = Depends(require_auth),
        task_id: int = Form(...),
        return_manager_id: str = Form(""),
        return_show_completed: str = Form(""),
        return_status: str = Form(""),
        return_kind: str = Form(""),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "tasks")
        t = await session.get(Task, task_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Task not found")
        assert_task_manage_access(user, t)
        if t.completed_at is None and t.deleted_at is None:
            t.completed_at = datetime.now(timezone.utc)
            await session.commit()
        qs = tasks_page_query(
            manager_id=int(return_manager_id.strip())
            if return_manager_id.strip().isdigit()
            else None,
            status=return_status.strip() or None,
            kind=return_kind.strip() or None,
            show_completed=return_show_completed.strip()
            in ("1", "true", "yes", "on"),
        )
        return RedirectResponse(f"/tasks{qs}", status_code=303)

    @app.post("/tasks/delete")
    async def tasks_delete(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth: Response | None = Depends(require_auth),
        task_id: int = Form(...),
        return_manager_id: str = Form(""),
        return_show_completed: str = Form(""),
        return_status: str = Form(""),
        return_kind: str = Form(""),
    ) -> Response:
        user = await load_web_user(request, session)
        require_nav(user, "tasks")
        t = await session.get(Task, task_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Task not found")
        assert_task_manage_access(user, t)
        t.deleted_at = datetime.now(timezone.utc)
        await session.commit()
        qs = tasks_page_query(
            manager_id=int(return_manager_id.strip())
            if return_manager_id.strip().isdigit()
            else None,
            status=return_status.strip() or None,
            kind=return_kind.strip() or None,
            show_completed=return_show_completed.strip()
            in ("1", "true", "yes", "on"),
        )
        return RedirectResponse(f"/tasks{qs}", status_code=303)
