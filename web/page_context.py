from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from web.auth import WebUser, get_web_user
from web.roles import (
    can_allocate_stand_stock,
    can_filter_managers,
    can_create_reserves,
    can_pick_reserve_manager,
    can_create_sale,
    can_create_tasks,
    can_manage_sales_plans,
    can_manage_tasks,
    can_operate_stand_warehouse,
    can_view_stand_warehouse,
    nav_allowed,
    panel_subtitle,
    scope_manager_id,
    show_pvc_clients_nav,
    show_stand_clients_nav,
)


def page_ctx(user: WebUser, **kwargs: object) -> dict[str, object]:
    return {
        "current_user": user,
        "is_admin": user.is_admin,
        "is_leader": user.is_leader,
        "is_manager": user.is_manager,
        "is_sales_manager": user.is_sales_manager,
        "can_filter_managers": can_filter_managers(user),
        "can_manage_tasks": can_manage_tasks(user),
        "can_manage_sales_plans": can_manage_sales_plans(user),
        "can_create_tasks": can_create_tasks(user),
        "can_create_reserves": can_create_reserves(user),
        "can_pick_reserve_manager": can_pick_reserve_manager(user),
        "can_create_sale": can_create_sale(user),
        "show_tasks_nav": nav_allowed(user, "tasks"),
        "show_stand_clients_nav": show_stand_clients_nav(user),
        "show_pvc_clients_nav": show_pvc_clients_nav(user),
        "is_pvc_section": False,
        "is_pvc_form": False,
        "can_allocate_stand_stock": can_allocate_stand_stock(user),
        "can_operate_stand_warehouse": can_operate_stand_warehouse(user),
        "can_view_stand_warehouse": can_view_stand_warehouse(user),
        "panel_subtitle": panel_subtitle(user),
        **kwargs,
    }


async def load_web_user(request: Request, session: AsyncSession) -> WebUser:
    return await get_web_user(request, session)


def scoped_manager_filter(user: WebUser, requested: int | None) -> int | None:
    return scope_manager_id(user, requested)
