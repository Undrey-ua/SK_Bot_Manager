from __future__ import annotations

from config.team import is_regional_manager
from database.models import User, UserRole
from database.repositories.user import UserRepository


USER_ROLE_LABELS: dict[str, str] = {
    UserRole.ADMIN.value: "Адміністратор",
    UserRole.LEADER.value: "Керівник",
    UserRole.MANAGER.value: "Регіональний менеджер",
    UserRole.SALES_MANAGER.value: "Менеджер зі збуту",
}


def sales_team_by_supervisor(users: list[User]) -> dict[int, list[User]]:
    """Менеджери збуту, згруповані за регіональним менеджером (supervisor_id)."""
    out: dict[int, list[User]] = {}
    for u in users:
        if u.role != UserRole.SALES_MANAGER.value or not u.supervisor_id:
            continue
        out.setdefault(u.supervisor_id, []).append(u)
    for team in out.values():
        team.sort(key=lambda x: x.name.casefold())
    return out

USER_ROLE_CHOICES: list[tuple[str, str]] = [
    (UserRole.LEADER.value, USER_ROLE_LABELS[UserRole.LEADER.value]),
    (UserRole.MANAGER.value, USER_ROLE_LABELS[UserRole.MANAGER.value]),
    (UserRole.SALES_MANAGER.value, USER_ROLE_LABELS[UserRole.SALES_MANAGER.value]),
    (UserRole.ADMIN.value, USER_ROLE_LABELS[UserRole.ADMIN.value]),
]

VALID_ROLES = frozenset(USER_ROLE_LABELS.keys())

USAGE_LABELS: dict[str, str] = {
    "clients": "клієнти",
    "visits": "візити",
    "sales": "продажі",
    "reserves": "резерви",
    "regions": "області",
    "stand_transfers": "переміщення стендів",
    "tasks": "задачі",
}


def role_choices_for_form(
    *,
    has_admin: bool,
    editing: User | None = None,
) -> list[tuple[str, str]]:
    """Роль admin — лише один; при редагуванні поточного адміна залишаємо в списку."""
    if has_admin and (editing is None or editing.role != UserRole.ADMIN.value):
        return [c for c in USER_ROLE_CHOICES if c[0] != UserRole.ADMIN.value]
    return list(USER_ROLE_CHOICES)


def user_role_label(role: str) -> str:
    return USER_ROLE_LABELS.get(role, role)


def user_roles_display(user: User) -> str:
    """Підпис ролі з урахуванням адміна, який також веде поле (Андрій Вовнянко)."""
    label = USER_ROLE_LABELS.get(user.role, user.role)
    if user.role == UserRole.ADMIN.value and is_regional_manager(user):
        regional = USER_ROLE_LABELS[UserRole.MANAGER.value]
        return f"{label}, {regional}"
    return label


def _format_usage_block(usage: dict[str, int]) -> str:
    parts = [
        f"{USAGE_LABELS[key]}: {usage[key]}"
        for key in USAGE_LABELS
        if usage.get(key, 0) > 0
    ]
    return ", ".join(parts)


async def delete_user_blocked_reason(
    repo: UserRepository,
    target: User,
    *,
    acting_user_id: int,
) -> str | None:
    if target.id == acting_user_id:
        return "Не можна видалити власний обліковий запис."
    if (
        target.role == UserRole.ADMIN.value
        and await repo.count_by_role(UserRole.ADMIN.value) <= 1
    ):
        return "Не можна видалити єдиного адміністратора системи."

    usage = await repo.related_usage_counts(target.id)
    if usage.get("supervisees", 0) > 0:
        return (
            "Спочатку переведіть або видаліть менеджерів зі збуту, "
            "привʼязаних до цього користувача."
        )
    block_parts = {k: v for k, v in usage.items() if k != "supervisees" and v > 0}
    if block_parts:
        return f"У користувача є дані в системі ({_format_usage_block(block_parts)})."
    return None


async def _validate_user_fields(
    repo: UserRepository,
    *,
    user_id: int | None,
    telegram_id: int,
    name: str,
    role: str,
    supervisor_id: int | None,
    regional_managers: list[User],
    target: User | None = None,
) -> str | None:
    name = name.strip()
    if not name:
        return "Вкажіть ПІБ користувача."
    if telegram_id <= 0:
        return "Невірний Telegram ID."
    if role not in VALID_ROLES:
        return "Невірна роль."

    existing = await repo.get_by_telegram_id(telegram_id)
    if existing is not None and (user_id is None or existing.id != user_id):
        return f"Telegram ID {telegram_id} вже використовується ({existing.name})."

    admin_count = await repo.count_by_role(UserRole.ADMIN.value)
    if role == UserRole.ADMIN.value:
        if target is None:
            if admin_count >= 1:
                return "В системі вже є адміністратор. Додайте лише одного."
        elif target.role != UserRole.ADMIN.value and admin_count >= 1:
            return "В системі вже є адміністратор."
    elif target is not None and target.role == UserRole.ADMIN.value and admin_count <= 1:
        return "Спочатку призначте іншого адміністратора, перш ніж змінювати роль."

    if role == UserRole.SALES_MANAGER.value:
        if supervisor_id is None:
            return "Для менеджера зі збуту оберіть регіонального менеджера."
        supervisor = next((m for m in regional_managers if m.id == supervisor_id), None)
        if supervisor is None:
            return "Обраний регіональний менеджер не знайдений."
        if user_id is not None and supervisor_id == user_id:
            return "Менеджер зі збуту не може бути керівником сам собі."
    elif supervisor_id is not None:
        return "Керівник регіонального менеджера лише для ролі «Менеджер зі збуту»."

    return None


async def validate_new_user(
    repo: UserRepository,
    *,
    telegram_id: int,
    name: str,
    role: str,
    supervisor_id: int | None,
    regional_managers: list[User],
) -> str | None:
    return await _validate_user_fields(
        repo,
        user_id=None,
        telegram_id=telegram_id,
        name=name,
        role=role,
        supervisor_id=supervisor_id,
        regional_managers=regional_managers,
    )


async def validate_update_user(
    repo: UserRepository,
    target: User,
    *,
    telegram_id: int,
    name: str,
    role: str,
    supervisor_id: int | None,
    regional_managers: list[User],
) -> str | None:
    return await _validate_user_fields(
        repo,
        user_id=target.id,
        telegram_id=telegram_id,
        name=name,
        role=role,
        supervisor_id=supervisor_id,
        regional_managers=regional_managers,
        target=target,
    )
