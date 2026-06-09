from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from bot.container import build_container
from config.settings import Settings, get_settings
from web.services.dashboard import DashboardService
from web.services.user_admin import user_role_label
from web.client_geo import client_city
from web.utils import (
    UK_MONTHS,
    WEEKDAY_LABELS,
    client_stands,
    format_date,
    format_dt,
    format_qty,
    format_signed_pct,
    format_signed_qty,
    task_label,
    tasks_page_query,
    visit_type_label,
    MANAGER_TASK_KIND_CHOICES,
    manager_task_kind_label,
    parse_manager_task_kind_filter,
)
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
    format_qty=format_qty,
    format_signed_qty=format_signed_qty,
    format_signed_pct=format_signed_pct,
    uk_months=UK_MONTHS,
    weekday_labels=WEEKDAY_LABELS,
    format_date=format_date,
    tasks_page_query=tasks_page_query,
    manager_task_kind_label=manager_task_kind_label,
    manager_task_kind_choices=MANAGER_TASK_KIND_CHOICES,
    user_role_label=user_role_label,
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
                manager_counts=await service.visits_per_manager()
                if can_filter_managers(user)
                else [],
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

    @app.get("/clients/{client_id}", response_class=HTMLResponse)
    async def client_detail(
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
            "client_detail.html",
            page_ctx(
                user,
                active_nav="clients",
                client=client,
                visit_count=await service.client_visit_count(client_id),
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

    @app.get("/clients", response_class=HTMLResponse)
    async def clients_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        service: DashboardService = Depends(dashboard_service),
        _auth: Response | None = Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_nav(user, "clients")
        all_clients = await service.list_clients()
        stands = await service.list_active_stands()
        filters = ClientFilters(
            manager_id=scoped_manager_filter(user, query_int(request, "manager_id")),
            region_id=query_int(request, "region_id"),
            city=query_str(request, "city"),
            stand_id=query_int(request, "stand_id"),
        )
        owner = data_owner_manager_id(user)
        pool = (
            all_clients
            if can_filter_managers(user)
            else [c for c in all_clients if c.manager_id == owner]
        )
        clients = filter_clients(pool, filters)
        filter_options = build_client_filter_options(
            pool,
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
        return templates.TemplateResponse(
            request,
            "clients.html",
            page_ctx(
                user,
                active_nav="clients",
                clients=clients,
                clients_total=len(pool),
                managers=await service.list_managers() if can_filter_managers(user) else [],
                selected_manager_id=filters.manager_id,
                selected_region_id=filters.region_id,
                selected_city=filters.city,
                selected_stand_id=filters.stand_id,
                filter_regions=filter_options.regions,
                filter_cities=filter_options.cities,
                filter_stands=filter_options.stands,
                has_filters=has_filters,
            ),
        )

    return app
