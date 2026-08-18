"""Сфера роботи регіонального менеджера: стенди, ПВХ або обидва."""

from __future__ import annotations

from enum import Enum

from database.models import User, UserRole, VisitType


class WorkScope(str, Enum):
    STAND = "stand"
    PVC = "pvc"
    BOTH = "both"


WORK_SCOPE_DEFAULT = WorkScope.STAND.value

WORK_SCOPE_LABELS: dict[str, str] = {
    WorkScope.STAND.value: "Стенди",
    WorkScope.PVC.value: "ПВХ",
    WorkScope.BOTH.value: "Стенди і ПВХ",
}

WORK_SCOPE_CHOICES: list[tuple[str, str]] = [
    (WorkScope.STAND.value, WORK_SCOPE_LABELS[WorkScope.STAND.value]),
    (WorkScope.PVC.value, WORK_SCOPE_LABELS[WorkScope.PVC.value]),
    (WorkScope.BOTH.value, WORK_SCOPE_LABELS[WorkScope.BOTH.value]),
]


def normalize_work_scope(value: str | None) -> str:
    if not value:
        return WORK_SCOPE_DEFAULT
    try:
        return WorkScope(value).value
    except ValueError:
        return WORK_SCOPE_DEFAULT


def work_scope_of(user: User | None) -> str:
    if user is None:
        return WORK_SCOPE_DEFAULT
    return normalize_work_scope(getattr(user, "work_scope", None))


def work_scope_label(value: str | None) -> str:
    return WORK_SCOPE_LABELS.get(normalize_work_scope(value), WORK_SCOPE_LABELS[WORK_SCOPE_DEFAULT])


def works_stands(user: User | None) -> bool:
    return work_scope_of(user) in {WorkScope.STAND.value, WorkScope.BOTH.value}


def works_pvc(user: User | None) -> bool:
    return work_scope_of(user) in {WorkScope.PVC.value, WorkScope.BOTH.value}


def is_dual_scope(user: User | None) -> bool:
    return work_scope_of(user) == WorkScope.BOTH.value


def default_visit_type(user: User | None) -> str:
    if works_pvc(user) and not works_stands(user):
        return VisitType.PVH.value
    return VisitType.STAND.value


def needs_work_scope(user: User | None, *, role: str | None = None) -> bool:
    """Сферу задають регіональним менеджерам (у т.ч. адміну з полем)."""
    from config.team import is_regional_manager

    if user is not None and is_regional_manager(user):
        return True
    resolved = role if role is not None else (user.role if user else None)
    return resolved == UserRole.MANAGER.value
