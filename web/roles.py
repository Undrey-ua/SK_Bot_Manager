"""Ролі та доступ у веб-панелі."""

from __future__ import annotations

from database.models import UserRole
from web.auth import WebUser

ORG_VIEW_ROLES = frozenset({UserRole.ADMIN.value, UserRole.LEADER.value})
TASK_MANAGER_ROLES = frozenset({UserRole.ADMIN.value, UserRole.LEADER.value})
REGIONAL_MANAGER_ROLE = UserRole.MANAGER.value
SALES_MANAGER_ROLE = UserRole.SALES_MANAGER.value

WEB_NAV_ALL = frozenset({
    "visits",
    "clients",
    "analytics",
    "reserves",
    "tasks",
    "stand_moves",
    "stand_warehouse",
    "users",
})

STAND_ALLOCATE_ROLES = frozenset({UserRole.ADMIN.value, UserRole.LEADER.value})
STAND_WAREHOUSE_OPS_ROLES = frozenset({UserRole.ADMIN.value, UserRole.MANAGER.value})
WEB_NAV_ADMIN_EXTRA = frozenset({"users"})
WEB_NAV_SALES_MANAGER = frozenset({"analytics", "reserves"})

# Розділи, які адмін може додати поверх ролі (насамперед менеджеру зі збуту).
WEB_NAV_GRANTABLE = frozenset({"visits", "clients", "tasks", "stand_warehouse"})
WEB_NAV_GRANT_LABELS: dict[str, str] = {
    "visits": "Візити",
    "clients": "Клієнти",
    "tasks": "Задачі",
    "stand_warehouse": "Склад стендів",
}
WEB_NAV_GRANT_CHOICES: list[tuple[str, str]] = [
    (key, WEB_NAV_GRANT_LABELS[key])
    for key in ("visits", "clients", "tasks", "stand_warehouse")
]


def parse_nav_grants(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    seen: list[str] = []
    for part in raw.replace(",", " ").split():
        key = part.strip()
        if key in WEB_NAV_GRANTABLE and key not in seen:
            seen.append(key)
    return tuple(seen)


def serialize_nav_grants(keys: list[str] | tuple[str, ...] | None) -> str:
    return ",".join(parse_nav_grants(",".join(keys or [])))


def role_default_nav_keys(role: str) -> frozenset[str]:
    if role == UserRole.ADMIN.value:
        return WEB_NAV_ALL
    if role == UserRole.LEADER.value:
        return WEB_NAV_ALL - WEB_NAV_ADMIN_EXTRA
    if role == UserRole.SALES_MANAGER.value:
        return WEB_NAV_SALES_MANAGER
    return WEB_NAV_ALL - {"users"}


def grantable_nav_choices_for_role(role: str) -> list[tuple[str, str]]:
    defaults = role_default_nav_keys(role)
    return [(key, label) for key, label in WEB_NAV_GRANT_CHOICES if key not in defaults]


def _granted_nav_keys(user: WebUser) -> frozenset[str]:
    grants = frozenset(getattr(user, "nav_grants", ()) or ()) & WEB_NAV_GRANTABLE
    if "stand_warehouse" in grants:
        grants = grants | {"stand_moves"}
    return grants


def work_scope_value(user: WebUser) -> str:
    from config.work_scope import normalize_work_scope

    return normalize_work_scope(getattr(user, "work_scope", None))


def client_work_scope(user: WebUser) -> str:
    """Сфера клієнтських баз: у менеджера збуту — як у регіонального керівника."""
    from config.work_scope import normalize_work_scope

    if is_sales_manager(user):
        return normalize_work_scope(
            getattr(user, "supervisor_work_scope", None)
            or getattr(user, "work_scope", None)
        )
    return work_scope_value(user)


def show_stand_clients_nav(user: WebUser) -> bool:
    if not nav_allowed(user, "clients"):
        return False
    if user.role in ORG_VIEW_ROLES:
        return True
    from config.work_scope import WorkScope

    return client_work_scope(user) in {WorkScope.STAND.value, WorkScope.BOTH.value}


def show_pvc_clients_nav(user: WebUser) -> bool:
    if not nav_allowed(user, "clients"):
        return False
    if user.role in ORG_VIEW_ROLES:
        return True
    from config.work_scope import WorkScope

    return client_work_scope(user) in {WorkScope.PVC.value, WorkScope.BOTH.value}


def can_filter_managers(user: WebUser) -> bool:
    return user.role in ORG_VIEW_ROLES


def can_manage_sales_plans(user: WebUser) -> bool:
    """Встановлення місячного плану продажів — адмін, керівник."""
    return user.role in TASK_MANAGER_ROLES


def can_manage_tasks(user: WebUser) -> bool:
    """Повний доступ до всіх задач (адмін, керівник)."""
    return user.role in TASK_MANAGER_ROLES


def can_create_tasks(user: WebUser) -> bool:
    """Додавання задач: адмін/керівник — будь-кому; менеджер — собі."""
    return can_manage_tasks(user) or user.role == REGIONAL_MANAGER_ROLE


def can_manage_task(user: WebUser, *, assignee_id: int) -> bool:
    """Редагування/видалення: адмін/керівник — усі; менеджер — лише свої (assignee)."""
    if can_manage_tasks(user):
        return True
    if user.role == REGIONAL_MANAGER_ROLE:
        return assignee_id == user.id
    return False


def can_allocate_stand_stock(user: WebUser) -> bool:
    return user.role in STAND_ALLOCATE_ROLES


def can_operate_stand_warehouse(user: WebUser) -> bool:
    return user.role in STAND_WAREHOUSE_OPS_ROLES


def can_view_stand_warehouse(user: WebUser) -> bool:
    return nav_allowed(user, "stand_warehouse")


def is_leader(user: WebUser) -> bool:
    return user.role == UserRole.LEADER.value


def is_sales_manager(user: WebUser) -> bool:
    return user.role == SALES_MANAGER_ROLE


def panel_subtitle(user: WebUser) -> str:
    if user.is_admin:
        return "Адміністратор"
    return user.name


def allowed_nav_keys(user: WebUser) -> frozenset[str]:
    return role_default_nav_keys(user.role) | _granted_nav_keys(user)


def nav_allowed(user: WebUser, key: str) -> bool:
    return key in allowed_nav_keys(user)


def scope_manager_id(user: WebUser | None, requested: int | None) -> int | None:
    if user is None:
        return requested
    if is_sales_manager(user):
        return user.supervisor_id
    if user.role == REGIONAL_MANAGER_ROLE:
        return user.id
    if user.role in ORG_VIEW_ROLES:
        return requested
    return user.id


def data_owner_manager_id(user: WebUser) -> int | None:
    """Чиї клієнти/візити (для менеджера збуту — регіонального)."""
    if is_sales_manager(user):
        return user.supervisor_id
    if user.role == REGIONAL_MANAGER_ROLE:
        return user.id
    return None


def default_owned_manager_id(user: WebUser) -> int:
    """Менеджер-власник картки клієнта при створенні з панелі."""
    owner = data_owner_manager_id(user)
    return owner if owner is not None else user.id


def show_reserves_manager_column(user: WebUser) -> bool:
    """Колонка «Менеджер» у резервах — для керівників і полевих менеджерів."""
    return user.role in ORG_VIEW_ROLES or user.role == REGIONAL_MANAGER_ROLE


def can_filter_reserves_managers(user: WebUser) -> bool:
    """Фільтр резервів за менеджером (регіональний менеджер бачить усіх)."""
    return show_reserves_manager_column(user)


def reserve_owner_manager_id(user: WebUser) -> int:
    """Власник резерву (для менеджера збуту — регіональний керівник)."""
    if is_sales_manager(user) and user.supervisor_id is not None:
        return user.supervisor_id
    return user.id


def form_owner_manager_id(user: WebUser) -> int:
    """Менеджер для каскадних форм (область → клієнт → бренд)."""
    return reserve_owner_manager_id(user)


def resolve_reserve_form_manager_id(
    user: WebUser,
    requested_manager_id: int | None,
) -> int:
    """Менеджер-власник резерву з форми (керівник обирає, полевий — сам)."""
    if can_pick_reserve_manager(user):
        if requested_manager_id is None:
            raise ValueError("manager_id required")
        return requested_manager_id
    return reserve_owner_manager_id(user)


def can_pick_reserve_manager(user: WebUser) -> bool:
    """Керівник/адмін обирає менеджера при додаванні резерву."""
    return user.role in ORG_VIEW_ROLES


def can_create_reserves(user: WebUser) -> bool:
    """Додавання резервів: адмін/керівник, регіональний і менеджер збуту."""
    return (
        user.role in TASK_MANAGER_ROLES
        or user.role == REGIONAL_MANAGER_ROLE
        or is_sales_manager(user)
    )


def can_manage_reserve(user: WebUser, *, manager_id: int) -> bool:
    """Редагування/скасування: адмін/керівник — усі; інші — лише свої."""
    if user.role in TASK_MANAGER_ROLES:
        return True
    return manager_id == reserve_owner_manager_id(user)


def can_sale_from_reserve(user: WebUser, *, manager_id: int) -> bool:
    """Продаж із резерву — лише автор резерву (як у боті)."""
    return manager_id == reserve_owner_manager_id(user)


def can_create_sale(user: WebUser) -> bool:
    """Додавання продажу з веб-панелі."""
    return nav_allowed(user, "analytics")


def can_manage_sale(user: WebUser, sale_manager_id: int) -> bool:
    """Редагування/видалення продажу — адмін або менеджер, який його додав."""
    if user.is_admin:
        return True
    if user.role == REGIONAL_MANAGER_ROLE and user.id == sale_manager_id:
        return True
    return False


def reserves_scope_manager_id(
    user: WebUser | None,
    requested: int | None,
) -> int | None:
    """Обмеження списку резервів: полевий менеджер — усі; збут — лише свого регіонального."""
    if user is None:
        return requested
    if is_sales_manager(user):
        return user.supervisor_id
    if user.role == REGIONAL_MANAGER_ROLE:
        return requested
    if user.role in ORG_VIEW_ROLES:
        return requested
    return requested
