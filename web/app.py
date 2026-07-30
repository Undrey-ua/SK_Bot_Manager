from __future__ import annotations

import hashlib
import secrets
from datetime import date as date_cls
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from bot.container import build_container
from config.settings import Settings, get_settings
from database.models import STAND_TRANSFER_OPERATION_LABELS, UserRole
from web.auth import (
    LoginRequired,
    assert_client_access,
    assert_visit_access,
    ensure_authenticated,
    get_first_admin,
    load_user_by_telegram_id,
    require_nav,
    set_session_user,
)
from web.deps import query_int, query_str
from web.page_context import load_web_user, page_ctx, scoped_manager_filter
from web.roles import can_filter_managers, data_owner_manager_id
from web.services.clients_filter import ClientFilters, build_client_filter_options
from web.services.dashboard import DashboardService
from config.team import is_regional_manager
from web.services.user_admin import user_role_label, user_roles_display
from web.client_geo import (
    client_city,
    client_display_city,
    client_display_comment,
    client_display_legal_name,
)
from web.client_sales_periods import (
    CLIENT_SALES_PERIOD_KINDS,
    CLIENT_SALES_PERIOD_LABELS,
    resolve_client_sales_period,
)
from web.utils import (
    UK_MONTHS,
    WEEKDAY_LABELS,
    client_has_equipment,
    client_stands,
    format_date,
    format_dt,
    format_qty,
    format_signed_pct,
    format_signed_qty,
    task_label,
    tasks_page_query,
    user_initials,
    visit_type_label,
    MANAGER_TASK_KIND_CHOICES,
    manager_task_kind_label,
    parse_manager_task_kind_filter,
)
from visit_task_labels import refresh_visit_task_labels
from web.roles import can_manage_reserve, can_manage_task, can_sale_from_reserve
from web.services.tasks_board import (
    TASK_STATUS_ACTIVE,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_OVERDUE,
    build_tasks_board,
)

WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
templates.env.globals.update(
    task_label=task_label,
    visit_type_label=visit_type_label,
    format_dt=format_dt,
    client_stands=client_stands,
    client_city=client_city,
    client_display_city=client_display_city,
    client_display_comment=client_display_comment,
    client_display_legal_name=client_display_legal_name,
    format_qty=format_qty,
    format_signed_qty=format_signed_qty,
    format_signed_pct=format_signed_pct,
    uk_months=UK_MONTHS,
    weekday_labels=WEEKDAY_LABELS,
    format_date=format_date,
    user_initials=user_initials,
    tasks_page_query=tasks_page_query,
    manager_task_kind_label=manager_task_kind_label,
    manager_task_kind_choices=MANAGER_TASK_KIND_CHOICES,
    can_manage_task=can_manage_task,
    can_manage_reserve=can_manage_reserve,
    can_sale_from_reserve=can_sale_from_reserve,
    user_role_label=user_role_label,
    user_roles_display=user_roles_display,
    is_regional_manager=is_regional_manager,
    stand_transfer_operation_label=lambda op: STAND_TRANSFER_OPERATION_LABELS.get(
        op, op
    ),
)

container = build_container()


def session_secret(settings: Settings) -> str:
    if settings.dashboard_secret_key.strip():
        return settings.dashboard_secret_key.strip()
    return hashlib.sha256(
        f"sk-dashboard:{settings.dashboard_password}".encode()
    ).hexdigest()


def _no_cache_html(response: HTMLResponse) -> HTMLResponse:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="SK Bot Manager — Панель керівника", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Швидка перевірка для Railway (без БД і сесії)."""
        return {"status": "ok"}

    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret(settings),
        session_cookie="sk_dashboard",
        max_age=60 * 60 * 24 * 14,
        https_only=False,
    )

    @app.exception_handler(LoginRequired)
    async def login_required_handler(_request: Request, exc: LoginRequired) -> RedirectResponse:
        return RedirectResponse(exc.url, status_code=303)

    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    async def get_session() -> AsyncSession:
        async with container.session_factory() as session:
            yield session

    def dashboard_service(session: AsyncSession = Depends(get_session)) -> DashboardService:
        return DashboardService(session)

    def require_auth(request: Request) -> None:
        ensure_authenticated(request)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if request.session.get("authenticated") and request.session.get("user_id"):
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": request.query_params.get("error")},
        )

    @app.post("/login")
    async def login_submit(
        request: Request,
        session: AsyncSession = Depends(get_session),
        password: str = Form(...),
        telegram_id: str = Form(""),
    ):
        tg_raw = telegram_id.strip()
        if tg_raw:
            manager_pwd = settings.dashboard_password
            if not manager_pwd or not secrets.compare_digest(password, manager_pwd):
                return RedirectResponse("/login?error=1", status_code=303)
            try:
                tg = int(tg_raw)
            except ValueError:
                return RedirectResponse("/login?error=telegram", status_code=303)
            user = await load_user_by_telegram_id(session, tg)
            if user is None:
                return RedirectResponse("/login?error=unknown", status_code=303)
            if user.role == UserRole.SALES_MANAGER.value and user.supervisor_id is None:
                return RedirectResponse("/login?error=no_supervisor", status_code=303)
            set_session_user(request, user)
            return RedirectResponse("/", status_code=303)

        admin_pwd = settings.dashboard_admin_password
        if not admin_pwd:
            return RedirectResponse("/login?error=manager_telegram", status_code=303)
        if not secrets.compare_digest(password, admin_pwd):
            return RedirectResponse("/login?error=1", status_code=303)

        admin = None
        if settings.dashboard_admin_telegram_id is not None:
            admin = await load_user_by_telegram_id(
                session, settings.dashboard_admin_telegram_id
            )
            if admin is None or admin.role != UserRole.ADMIN.value:
                return RedirectResponse("/login?error=no_admin", status_code=303)
        else:
            admin = await get_first_admin(session)
            if admin is None:
                return RedirectResponse("/login?error=no_admin", status_code=303)

        set_session_user(request, admin)
        return RedirectResponse("/", status_code=303)

    @app.get("/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    async def visits_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
        page: int = 1,
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        if user.is_sales_manager:
            return RedirectResponse("/analytics?section=sales", status_code=303)
        require_nav(user, "visits")
        manager_id = scoped_manager_filter(user, query_int(request, "manager_id"))
        visits, total, page, total_pages = await service.list_visits(
            manager_id=manager_id,
            page=page,
        )

        return templates.TemplateResponse(
            request,
            "visits.html",
            page_ctx(
                user,
                active_nav="visits",
                visits=visits,
                managers=await service.list_managers() if can_filter_managers(user) else [],
                stats=await service.visit_stats(manager_id=manager_id),
                selected_manager_id=manager_id,
                page=page,
                total_pages=total_pages,
                total=total,
            ),
        )

    @app.get("/visits/{visit_id}", response_class=HTMLResponse)
    async def visit_detail(
        request: Request,
        visit_id: int,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "visits")
        await assert_visit_access(session, user, visit_id)
        visit = await service.get_visit(visit_id)
        if visit is None:
            raise HTTPException(status_code=404, detail="Візит не знайдено")
        return templates.TemplateResponse(
            request,
            "visit_detail.html",
            page_ctx(user, active_nav="visits", visit=visit),
        )

    from web.routes_extra import register_extra_routes

    register_extra_routes(
        app,
        templates=templates,
        get_session=get_session,
        require_auth=require_auth,
        dashboard_service=dashboard_service,
    )

    async def _render_clients_list(
        request: Request,
        service: DashboardService,
        user,
        *,
        is_potential_section: bool,
        page: int,
    ) -> HTMLResponse:
        stands = await service.list_active_stands()
        is_potential = is_potential_section
        filters = ClientFilters(
            manager_id=scoped_manager_filter(user, query_int(request, "manager_id")),
            region_id=query_int(request, "region_id"),
            city=query_str(request, "city"),
            stand_id=query_int(request, "stand_id"),
            is_potential=is_potential,
        )
        owner = data_owner_manager_id(user)
        filter_pool_manager = filters.manager_id
        if not can_filter_managers(user):
            filter_pool_manager = owner
        filter_clients_pool = await service.list_clients_for_filters(
            manager_id=filter_pool_manager,
            is_potential=is_potential,
        )
        clients, clients_total, page, total_pages = await service.list_clients_page(
            filters,
            page=page,
        )
        filter_options = build_client_filter_options(
            filter_clients_pool,
            stands,
            manager_id=filters.manager_id,
            region_id=filters.region_id,
        )
        has_filters = any(
            [
                filters.manager_id is not None,
                filters.region_id is not None,
                filters.city,
                filters.stand_id is not None,
            ]
        )
        list_base_path = "/clients/potential" if is_potential_section else "/clients"
        return templates.TemplateResponse(
            request,
            "clients.html",
            page_ctx(
                user,
                active_nav="clients",
                clients_subsection="potential" if is_potential_section else "active",
                is_potential_section=is_potential_section,
                clients=clients,
                clients_total=clients_total,
                managers=await service.list_managers() if can_filter_managers(user) else [],
                filter_regions=filter_options.regions,
                filter_cities=filter_options.cities,
                filter_stands=filter_options.stands,
                selected_manager_id=filters.manager_id,
                selected_region_id=filters.region_id,
                selected_city=filters.city,
                selected_stand_id=filters.stand_id,
                has_filters=has_filters,
                list_base_path=list_base_path,
                page=page,
                total_pages=total_pages,
            ),
        )

    @app.get("/clients", response_class=HTMLResponse)
    async def clients_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
        page: int = 1,
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "clients")
        return await _render_clients_list(
            request, service, user, is_potential_section=False, page=page
        )

    @app.get("/clients/potential", response_class=HTMLResponse)
    async def potential_clients_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
        page: int = 1,
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "clients")
        return await _render_clients_list(
            request, service, user, is_potential_section=True, page=page
        )

    @app.get("/clients/{client_id}", response_class=HTMLResponse)
    async def client_detail(
        request: Request,
        client_id: int,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
        period_kind: str = "current",
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "clients")
        await assert_client_access(session, user, client_id)
        client = await service.get_client(client_id)
        if client is None:
            raise HTTPException(status_code=404, detail="Клієнта не знайдено")

        today = date_cls.today()
        period_kind = (
            period_kind if period_kind in CLIENT_SALES_PERIOD_KINDS else "current"
        )
        year = query_int(request, "year", default=today.year) or today.year
        quarter = (
            query_int(request, "quarter", default=(today.month - 1) // 3 + 1)
            or (today.month - 1) // 3 + 1
        )
        brand_id = query_int(request, "brand_id")

        period = resolve_client_sales_period(
            period_kind,
            today=today,
            year=year,
            quarter=quarter,
        )
        sales_rows, sales_total = await service.client_sales_in_period(
            client_id,
            period,
            brand_id=brand_id,
        )
        sales_by_brand = await service.client_sales_by_brand(
            client_id,
            period,
            brand_id=brand_id,
        )
        brands = await service.list_active_brands()
        sales_has_filters = brand_id is not None

        return templates.TemplateResponse(
            request,
            "client_detail.html",
            page_ctx(
                user,
                active_nav="clients",
                clients_subsection="potential" if client.is_potential else "active",
                client=client,
                visit_count=await service.client_visit_count(client_id),
                visit_gallery=await service.client_visit_gallery(client_id),
                period_kind=period_kind,
                year=year,
                quarter=quarter,
                period_label=period.label,
                sales_rows=sales_rows,
                sales_total=sales_total,
                sales_by_brand=sales_by_brand,
                filter_brands=[(b.id, b.name) for b in brands if b.is_active],
                selected_brand_id=brand_id,
                sales_has_filters=sales_has_filters,
                client_sales_period_labels=CLIENT_SALES_PERIOD_LABELS,
                client_has_equipment=client_has_equipment(client),
            ),
        )

    @app.get("/clients/{client_id}/visits", response_class=HTMLResponse)
    async def client_visits_history(
        request: Request,
        client_id: int,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "clients")
        await assert_client_access(session, user, client_id)
        client = await service.get_client(client_id)
        if client is None:
            raise HTTPException(status_code=404, detail="Клієнта не знайдено")
        return templates.TemplateResponse(
            request,
            "client_visits.html",
            page_ctx(
                user,
                active_nav="clients",
                client=client,
                visits=await service.list_client_visits(client_id),
            ),
        )

    from web.routes_panel import register_panel_routes
    from web.routes_users import register_user_routes

    register_panel_routes(
        app,
        templates=templates,
        get_session=get_session,
        require_auth=require_auth,
        dashboard_service=dashboard_service,
        settings=settings,
    )
    register_user_routes(
        app,
        templates=templates,
        get_session=get_session,
        require_auth=require_auth,
        dashboard_service=dashboard_service,
    )

    from web.routes_form_api import register_form_api_routes
    from web.routes_visit_tasks import register_visit_task_routes

    register_form_api_routes(
        app,
        get_session=get_session,
        require_auth=require_auth,
    )
    register_visit_task_routes(
        app,
        templates=templates,
        get_session=get_session,
        require_auth=require_auth,
    )

    @app.on_event("startup")
    async def load_visit_task_labels() -> None:
        async with container.session_factory() as session:
            await refresh_visit_task_labels(session)

    return app
