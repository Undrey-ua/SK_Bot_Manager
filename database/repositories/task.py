from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Task, User, normalize_manager_task_kind
from database.repositories.base import BaseRepository


class TaskRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    def _detail_options(self):
        return (selectinload(Task.created_by),)

    async def create(
        self,
        *,
        assignee_id: int,
        created_by_id: int,
        title: str,
        deadline: date | None,
        weekday: int | None,
        comment: str | None,
        kind: str | None = None,
    ) -> Task:
        task = Task(
            assignee_id=assignee_id,
            created_by_id=created_by_id,
            title=title.strip(),
            deadline=deadline,
            weekday=weekday,
            comment=comment.strip() if comment else None,
            kind=normalize_manager_task_kind(kind),
        )
        self._session.add(task)
        await self._session.flush()
        return task

    async def list_for_user(
        self,
        assignee_id: int,
        *,
        weekday: int | None = None,
        include_completed: bool = False,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.assignee_id == assignee_id, Task.deleted_at.is_(None))
            .options(*self._detail_options())
            .order_by(Task.deadline.asc().nullslast(), Task.created_at.desc())
        )
        if weekday is not None:
            stmt = stmt.where(Task.weekday == weekday)
        if not include_completed:
            stmt = stmt.where(Task.completed_at.is_(None))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, task_id: int) -> Task | None:
        result = await self._session.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(*self._detail_options())
        )
        return result.scalar_one_or_none()

    async def complete(self, task_id: int) -> Task | None:
        task = await self.get_by_id(task_id)
        if task is None:
            return None
        task.completed_at = datetime.now(timezone.utc)
        await self._session.flush()
        return task

    async def reopen(self, task_id: int) -> Task | None:
        task = await self.get_by_id(task_id)
        if task is None:
            return None
        task.completed_at = None
        await self._session.flush()
        return task

    async def set_deadline(self, task_id: int, deadline: date | None, comment: str | None) -> Task | None:
        task = await self.get_by_id(task_id)
        if task is None:
            return None
        task.deadline = deadline
        task.comment = comment.strip() if comment else task.comment
        await self._session.flush()
        return task

    async def delete(self, task_id: int) -> Task | None:
        task = await self.get_by_id(task_id)
        if task is None:
            return None
        task.deleted_at = datetime.now(timezone.utc)
        await self._session.flush()
        return task

    async def list_due_weekday(self, weekday: int, *, day: date) -> list[Task]:
        result = await self._session.execute(
            select(Task)
            .where(
                Task.weekday == weekday,
                Task.deleted_at.is_(None),
                Task.completed_at.is_(None),
                (Task.reminder_sent_on.is_(None) | (Task.reminder_sent_on != day)),
            )
            .options(*self._detail_options())
        )
        return list(result.scalars().all())

    async def mark_reminded(self, task_id: int, day: date) -> None:
        task = await self.get_by_id(task_id)
        if task is None:
            return
        task.reminder_sent_on = day
        await self._session.flush()

