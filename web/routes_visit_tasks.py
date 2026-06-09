"""Стандартні задачі візитів (бот) — лише адмін."""

from __future__ import annotations

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import VisitTask, VisitTaskType
from database.repositories.visit_task_type import VisitTaskTypeRepository
from visit_task_labels import refresh_visit_task_labels
from web.auth import require_admin
from web.page_context import load_web_user, page_ctx
from web.visit_task_codes import slug_visit_task_code


def register_visit_task_routes(app, *, templates, get_session, require_auth):
    @app.get("/admin/visit-tasks", response_class=HTMLResponse)
    async def visit_tasks_admin_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_admin(user)
        repo = VisitTaskTypeRepository(session)
        types = await repo.list_all()
        usage: dict[str, int] = {}
        rows = await session.execute(
            select(VisitTask.task, func.count())
            .group_by(VisitTask.task)
        )
        for code, count in rows.all():
            usage[str(code)] = int(count)
        return templates.TemplateResponse(
            request,
            "visit_task_types.html",
            page_ctx(
                user,
                active_nav="visit_tasks",
                task_types=types,
                usage_counts=usage,
            ),
        )

    @app.get("/admin/visit-tasks/new", response_class=HTMLResponse)
    async def visit_task_new_page(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_admin(user)
        return templates.TemplateResponse(
            request,
            "visit_task_type_form.html",
            page_ctx(
                user,
                active_nav="visit_tasks",
                task_type=None,
                form_action="/admin/visit-tasks/new",
                submit_label="Додати",
                form_label="",
                form_code="",
                form_sort_order=100,
                form_is_active=True,
            ),
        )

    @app.post("/admin/visit-tasks/new")
    async def visit_task_create(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        label: str = Form(...),
        code: str = Form(""),
        sort_order: int = Form(100),
    ) -> RedirectResponse:
        user = await load_web_user(request, session)
        require_admin(user)
        label = label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="Вкажіть назву")
        task_code = (code.strip() or slug_visit_task_code(label))[:50]
        repo = VisitTaskTypeRepository(session)
        if await repo.get_by_code(task_code):
            raise HTTPException(status_code=400, detail="Такий код уже існує")
        await repo.create(code=task_code, label=label, sort_order=sort_order)
        await refresh_visit_task_labels(session)
        await session.commit()
        return RedirectResponse("/admin/visit-tasks", status_code=303)

    @app.get("/admin/visit-tasks/{type_id}/edit", response_class=HTMLResponse)
    async def visit_task_edit_page(
        request: Request,
        type_id: int,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> HTMLResponse:
        user = await load_web_user(request, session)
        require_admin(user)
        row = await VisitTaskTypeRepository(session).get_by_id(type_id)
        if row is None:
            raise HTTPException(status_code=404)
        return templates.TemplateResponse(
            request,
            "visit_task_type_form.html",
            page_ctx(
                user,
                active_nav="visit_tasks",
                task_type=row,
                form_action=f"/admin/visit-tasks/{type_id}/edit",
                submit_label="Зберегти",
                form_label=row.label,
                form_code=row.code,
                form_sort_order=row.sort_order,
                form_is_active=row.is_active,
            ),
        )

    @app.post("/admin/visit-tasks/{type_id}/edit")
    async def visit_task_edit_save(
        request: Request,
        type_id: int,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
        label: str = Form(...),
        sort_order: int = Form(0),
        is_active: str = Form(""),
    ) -> RedirectResponse:
        user = await load_web_user(request, session)
        require_admin(user)
        repo = VisitTaskTypeRepository(session)
        updated = await repo.update(
            type_id,
            label=label,
            sort_order=sort_order,
            is_active=is_active.strip() in ("1", "true", "on", "yes"),
        )
        if updated is None:
            raise HTTPException(status_code=404)
        await refresh_visit_task_labels(session)
        await session.commit()
        return RedirectResponse("/admin/visit-tasks", status_code=303)

    @app.post("/admin/visit-tasks/{type_id}/delete")
    async def visit_task_delete(
        request: Request,
        type_id: int,
        session: AsyncSession = Depends(get_session),
        _auth=Depends(require_auth),
    ) -> RedirectResponse:
        user = await load_web_user(request, session)
        require_admin(user)
        repo = VisitTaskTypeRepository(session)
        row = await repo.get_by_id(type_id)
        if row is None:
            raise HTTPException(status_code=404)
        used = await session.scalar(
            select(func.count()).where(VisitTask.task == row.code)
        )
        if used:
            raise HTTPException(
                status_code=400,
                detail="Задача вже використовується у візитах — деактивуйте замість видалення",
            )
        await repo.delete(type_id)
        await refresh_visit_task_labels(session)
        await session.commit()
        return RedirectResponse("/admin/visit-tasks", status_code=303)
