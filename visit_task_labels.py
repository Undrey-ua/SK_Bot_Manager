"""Кеш підписів стандартних задач візиту (бот + веб)."""

from __future__ import annotations

from database.models import TASK_LABELS, TaskType
from database.repositories.visit_task_type import VisitTaskTypeRepository
from sqlalchemy.ext.asyncio import AsyncSession

_DEFAULT_LABELS: dict[str, str] = {t.value: TASK_LABELS[t] for t in TaskType}
_labels_cache: dict[str, str] = dict(_DEFAULT_LABELS)


async def refresh_visit_task_labels(session: AsyncSession) -> dict[str, str]:
    global _labels_cache
    db_labels = await VisitTaskTypeRepository(session).labels_map()
    _labels_cache = {**_DEFAULT_LABELS, **db_labels}
    return dict(_labels_cache)


def visit_task_label(code: str) -> str:
    return _labels_cache.get(code, code)


def visit_task_labels_snapshot() -> dict[str, str]:
    return dict(_labels_cache)
