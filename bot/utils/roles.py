"""Ролі та ефективний менеджер для операцій у боті."""

from __future__ import annotations

from database.models import User, UserRole

SALES_MANAGER_BLOCKED_CALLBACK_PREFIXES = (
    "clients:",
    "client:",
    "visit:",
    "tasks:",
    "regions:",
    "admin:",
)


def effective_manager_id(user: User) -> int:
    if user.role == UserRole.SALES_MANAGER.value and user.supervisor_id is not None:
        return user.supervisor_id
    return user.id


def is_sales_manager(user: User) -> bool:
    return user.role == UserRole.SALES_MANAGER.value


def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN.value


def is_leader(user: User) -> bool:
    return user.role == UserRole.LEADER.value


def can_manage_stand_catalog(user: User) -> bool:
    return is_admin(user)


def callback_allowed_for_user(user: User, callback_data: str) -> bool:
    if not is_sales_manager(user):
        return True
    if callback_data in ("menu:main",):
        return True
    if callback_data.startswith(("reserve:", "sale:", "menu:")):
        return True
    return not callback_data.startswith(SALES_MANAGER_BLOCKED_CALLBACK_PREFIXES)
