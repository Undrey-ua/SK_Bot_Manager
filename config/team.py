"""Відомі учасники команди (telegram_id, ПІБ).

Регіональний менеджер у полі — це той, хто веде клієнтів/візити (за telegram_id).
Роль у БД може бути `manager` або `admin` (Андрій Вовнянко — обидва).
"""

from __future__ import annotations

from database.models import User, UserRole

# telegram_id, ПІБ
REGIONAL_MANAGERS: tuple[tuple[int, str], ...] = (
    (535827585, "Андрій Вовнянко"),
    (5009921383, "Роман Ковальов"),
    (7770797356, "Павло Ковалишин"),
)

REGIONAL_MANAGER_TELEGRAM_IDS = frozenset(tg for tg, _ in REGIONAL_MANAGERS)

# Адмін, який також веде своє поле як регіональний менеджер
ADMIN_REGIONAL_MANAGER_TELEGRAM_IDS = frozenset({535827585})


def is_regional_manager(user: User) -> bool:
    """Полевий менеджер: role=manager або відомий telegram (напр. admin+поле)."""
    if user.role == UserRole.MANAGER.value:
        return True
    return user.telegram_id in REGIONAL_MANAGER_TELEGRAM_IDS


def filter_regional_managers(users: list[User]) -> list[User]:
    return [u for u in users if is_regional_manager(u)]
