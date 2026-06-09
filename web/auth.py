from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import User, UserRole
from database.repositories.user import UserRepository


@dataclass(frozen=True)
class WebUser:
    id: int
    name: str
    role: str
    telegram_id: int
    supervisor_id: int | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value

    @property
    def is_leader(self) -> bool:
        return self.role == UserRole.LEADER.value

    @property
    def is_manager(self) -> bool:
        return self.role == UserRole.MANAGER.value

    @property
    def is_sales_manager(self) -> bool:
        return self.role == UserRole.SALES_MANAGER.value


async def load_user_by_telegram_id(
    session: AsyncSession,
    telegram_id: int,
) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def load_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await UserRepository(session).get_by_id(user_id)


async def get_first_admin(session: AsyncSession) -> User | None:
    result = await session.execute(
        select(User).where(User.role == UserRole.ADMIN.value).order_by(User.id).limit(1)
    )
    return result.scalar_one_or_none()


def user_from_session(request: Request) -> WebUser | None:
    if not request.session.get("authenticated"):
        return None
    uid = request.session.get("user_id")
    if uid is None:
        return None
    return WebUser(
        id=int(uid),
        name=str(request.session.get("user_name") or ""),
        role=str(request.session.get("user_role") or UserRole.MANAGER.value),
        telegram_id=int(request.session.get("telegram_id") or 0),
    )


def set_session_user(request: Request, user: User) -> None:
    request.session["authenticated"] = True
    request.session["user_id"] = user.id
    request.session["user_name"] = user.name
    request.session["user_role"] = user.role
    request.session["telegram_id"] = user.telegram_id


def set_session_admin_fallback(request: Request, admin: User) -> None:
    """Вхід лише паролем керівника (без Telegram ID)."""
    set_session_user(request, admin)


class LoginRequired(Exception):
    """Потрібен вхід у веб-панель — обробник перенаправляє на /login."""

    def __init__(self, url: str = "/login") -> None:
        self.url = url


def require_auth_redirect(request: Request) -> RedirectResponse | None:
    if not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)
    if request.session.get("user_id") is None:
        return RedirectResponse("/login?error=session", status_code=303)
    return None


def ensure_authenticated(request: Request) -> None:
    redirect = require_auth_redirect(request)
    if redirect is not None:
        location = redirect.headers.get("location", "/login")
        raise LoginRequired(location)


async def get_web_user(
    request: Request,
    session: AsyncSession,
) -> WebUser:
    ensure_authenticated(request)
    cached = user_from_session(request)
    if cached is None:
        request.session.clear()
        raise LoginRequired("/login?error=session")
    db_user = await load_user_by_id(session, cached.id)
    if db_user is None:
        request.session.clear()
        raise LoginRequired("/login?error=session")
    return WebUser(
        id=db_user.id,
        name=db_user.name,
        role=db_user.role,
        telegram_id=db_user.telegram_id,
        supervisor_id=db_user.supervisor_id,
    )


def require_admin(user: WebUser) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")


def require_task_manager(user: WebUser) -> None:
    from web.roles import can_manage_tasks

    if not can_manage_tasks(user):
        raise HTTPException(status_code=403, detail="Forbidden")


def require_task_create(user: WebUser) -> None:
    from web.roles import can_create_tasks

    if not can_create_tasks(user):
        raise HTTPException(status_code=403, detail="Forbidden")


def assert_task_manage_access(user: WebUser, task) -> None:
    from web.roles import can_manage_task

    if not can_manage_task(user, assignee_id=task.assignee_id):
        raise HTTPException(status_code=403, detail="Forbidden")


def require_reserve_create(user: WebUser) -> None:
    from web.roles import can_create_reserves

    if not can_create_reserves(user):
        raise HTTPException(status_code=403, detail="Forbidden")


def assert_reserve_manage_access(user: WebUser, reserve) -> None:
    from web.roles import can_manage_reserve

    if not can_manage_reserve(user, manager_id=reserve.manager_id):
        raise HTTPException(status_code=403, detail="Forbidden")


def require_sale_create(user: WebUser) -> None:
    from web.roles import can_create_sale

    if not can_create_sale(user):
        raise HTTPException(status_code=403, detail="Forbidden")


def require_nav(user: WebUser, nav_key: str) -> None:
    from web.roles import nav_allowed

    if not nav_allowed(user, nav_key):
        raise HTTPException(status_code=403, detail="Forbidden")


async def assert_client_access(
    session: AsyncSession,
    user: WebUser,
    client_id: int,
) -> None:
    from web.roles import ORG_VIEW_ROLES, data_owner_manager_id

    if user.role in ORG_VIEW_ROLES:
        return
    from database.models import Client

    result = await session.execute(
        select(Client.manager_id).where(Client.id == client_id)
    )
    mid = result.scalar_one_or_none()
    if mid is None:
        raise HTTPException(status_code=404, detail="Client not found")
    owner = data_owner_manager_id(user)
    if owner is None or mid != owner:
        raise HTTPException(status_code=403, detail="Forbidden")


async def assert_sale_manage_access(
    session: AsyncSession,
    user: WebUser,
    sale_id: int,
) -> int:
    from database.models import Sale
    from web.roles import can_manage_sale

    result = await session.execute(
        select(Sale.manager_id).where(Sale.id == sale_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    manager_id = row[0]
    if not can_manage_sale(user, manager_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    return manager_id


async def assert_visit_access(
    session: AsyncSession,
    user: WebUser,
    visit_id: int,
) -> None:
    from web.roles import ORG_VIEW_ROLES, data_owner_manager_id

    if user.role in ORG_VIEW_ROLES:
        return
    from database.models import Visit

    result = await session.execute(
        select(Visit.manager_id).where(Visit.id == visit_id)
    )
    mid = result.scalar_one_or_none()
    if mid is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    owner = data_owner_manager_id(user)
    if owner is None or mid != owner:
        raise HTTPException(status_code=403, detail="Forbidden")
