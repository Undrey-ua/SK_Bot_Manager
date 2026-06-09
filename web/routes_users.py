"""Керування користувачами (лише адмін)."""

from __future__ import annotations

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, UserRole
from database.repositories.user import UserRepository
from web.auth import require_admin
from web.page_context import load_web_user, page_ctx
from web.services.dashboard import DashboardService
from web.services.user_admin import (
    delete_user_blocked_reason,
    role_choices_for_form,
    sales_team_by_supervisor,
    validate_new_user,
    validate_update_user,
)


def _parse_user_form(
    *,
    name: str,
    telegram_id: str,
    role: str,
    supervisor_id: str,
) -> tuple[int, str, str, int | None]:
    try:
        tg = int(telegram_id.strip())
    except ValueError:
        tg = -1
    sup_id = int(supervisor_id.strip()) if supervisor_id.strip().isdigit() else None
    return tg, name, role.strip(), sup_id


def register_user_routes(app, *, templates, get_session, require_auth, dashboard_service):
    async def _user_form_ctx(
        request: Request,
        session: AsyncSession,
        dashboard: DashboardService,
        *,
        edit_user: User | None,
        form_name: str,
        form_telegram_id: str,
        form_role: str,
        form_supervisor_id: int | None,
        error: str | None,
        acting_user: User,
    ) -> dict:
        repo = UserRepository(session)
        has_admin = await repo.count_by_role(UserRole.ADMIN.value) >= 1
        delete_blocked = None
        if edit_user is not None:
            delete_blocked = await delete_user_blocked_reason(
                repo,
                edit_user,
                acting_user_id=acting_user.id,
            )
        return page_ctx(
            acting_user,
            active_nav="users",
            edit_user=edit_user,
            form_action=(
                f"/admin/users/{edit_user.id}/edit"
                if edit_user
                else "/admin/users/new"
            ),
            submit_label="Зберегти" if edit_user else "Створити",
            role_choices=role_choices_for_form(has_admin=has_admin, editing=edit_user),
            regional_managers=await dashboard.list_managers(),
            form_name=form_name,
            form_telegram_id=form_telegram_id,
            form_role=form_role,
            form_supervisor_id=form_supervisor_id,
            error=error,
            delete_blocked=delete_blocked,
        )

    @app.get("/admin/users", response_class=HTMLResponse)
    async def users_list(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ):
        user = await load_web_user(request, session)
        require_admin(user)
        repo = UserRepository(session)
        users = await repo.list_all()
        qp = request.query_params
        return templates.TemplateResponse(
            request,
            "users.html",
            page_ctx(
                user,
                active_nav="users",
                users=users,
                sales_team=sales_team_by_supervisor(users),
                created=qp.get("created") == "1",
                updated=qp.get("updated") == "1",
                deleted=qp.get("deleted") == "1",
            ),
        )

    @app.get("/admin/users/new", response_class=HTMLResponse)
    async def user_new_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
    ):
        user = await load_web_user(request, session)
        require_admin(user)
        return templates.TemplateResponse(
            request,
            "user_form.html",
            await _user_form_ctx(
                request,
                session,
                dashboard,
                edit_user=None,
                form_name="",
                form_telegram_id="",
                form_role=UserRole.MANAGER.value,
                form_supervisor_id=None,
                error=None,
                acting_user=user,
            ),
        )

    @app.post("/admin/users/new")
    async def user_new_save(
        request: Request,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
        name: str = Form(...),
        telegram_id: str = Form(...),
        role: str = Form(...),
        supervisor_id: str = Form(""),
    ):
        user = await load_web_user(request, session)
        require_admin(user)
        repo = UserRepository(session)
        regional = await dashboard.list_managers()
        tg, name_s, role_s, sup_id = _parse_user_form(
            name=name,
            telegram_id=telegram_id,
            role=role,
            supervisor_id=supervisor_id,
        )
        err = await validate_new_user(
            repo,
            telegram_id=tg,
            name=name_s,
            role=role_s,
            supervisor_id=sup_id,
            regional_managers=regional,
        )
        if err:
            return templates.TemplateResponse(
                request,
                "user_form.html",
                await _user_form_ctx(
                    request,
                    session,
                    dashboard,
                    edit_user=None,
                    form_name=name_s,
                    form_telegram_id=telegram_id.strip(),
                    form_role=role_s,
                    form_supervisor_id=sup_id,
                    error=err,
                    acting_user=user,
                ),
                status_code=400,
            )

        await repo.create(
            telegram_id=tg,
            name=name_s,
            role=role_s,
            supervisor_id=sup_id if role_s == UserRole.SALES_MANAGER.value else None,
        )
        await session.commit()
        return RedirectResponse("/admin/users?created=1", status_code=303)

    @app.get("/admin/users/{user_id}/edit", response_class=HTMLResponse)
    async def user_edit_page(
        request: Request,
        user_id: int,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
    ):
        user = await load_web_user(request, session)
        require_admin(user)
        target = await UserRepository(session).get_by_id(user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Користувача не знайдено")
        return templates.TemplateResponse(
            request,
            "user_form.html",
            await _user_form_ctx(
                request,
                session,
                dashboard,
                edit_user=target,
                form_name=target.name,
                form_telegram_id=str(target.telegram_id),
                form_role=target.role,
                form_supervisor_id=target.supervisor_id,
                error=None,
                acting_user=user,
            ),
        )

    @app.post("/admin/users/{user_id}/edit")
    async def user_edit_save(
        request: Request,
        user_id: int,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
        name: str = Form(...),
        telegram_id: str = Form(...),
        role: str = Form(...),
        supervisor_id: str = Form(""),
    ):
        user = await load_web_user(request, session)
        require_admin(user)
        repo = UserRepository(session)
        target = await repo.get_by_id(user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Користувача не знайдено")
        regional = await dashboard.list_managers()
        tg, name_s, role_s, sup_id = _parse_user_form(
            name=name,
            telegram_id=telegram_id,
            role=role,
            supervisor_id=supervisor_id,
        )
        err = await validate_update_user(
            repo,
            target,
            telegram_id=tg,
            name=name_s,
            role=role_s,
            supervisor_id=sup_id,
            regional_managers=regional,
        )
        if err:
            return templates.TemplateResponse(
                request,
                "user_form.html",
                await _user_form_ctx(
                    request,
                    session,
                    dashboard,
                    edit_user=target,
                    form_name=name_s,
                    form_telegram_id=telegram_id.strip(),
                    form_role=role_s,
                    form_supervisor_id=sup_id,
                    error=err,
                    acting_user=user,
                ),
                status_code=400,
            )

        await repo.update(
            target,
            name=name_s,
            telegram_id=tg,
            role=role_s,
            supervisor_id=sup_id,
        )
        await session.commit()
        return RedirectResponse("/admin/users?updated=1", status_code=303)

    @app.post("/admin/users/{user_id}/delete")
    async def user_delete(
        request: Request,
        user_id: int,
        session: AsyncSession = Depends(get_session),
        dashboard: DashboardService = Depends(dashboard_service),
        _auth=Depends(require_auth),
    ):
        user = await load_web_user(request, session)
        require_admin(user)
        repo = UserRepository(session)
        target = await repo.get_by_id(user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Користувача не знайдено")

        err = await delete_user_blocked_reason(
            repo, target, acting_user_id=user.id
        )
        if err:
            return templates.TemplateResponse(
                request,
                "user_form.html",
                await _user_form_ctx(
                    request,
                    session,
                    dashboard,
                    edit_user=target,
                    form_name=target.name,
                    form_telegram_id=str(target.telegram_id),
                    form_role=target.role,
                    form_supervisor_id=target.supervisor_id,
                    error=err,
                    acting_user=user,
                ),
                status_code=400,
            )

        await repo.delete(target)
        await session.commit()
        return RedirectResponse("/admin/users?deleted=1", status_code=303)
