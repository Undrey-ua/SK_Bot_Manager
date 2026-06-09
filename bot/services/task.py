from __future__ import annotations

from datetime import date

from database.models import Task
from database.repositories.task import TaskRepository


class TaskService:
    def __init__(self, repo: TaskRepository) -> None:
        self._repo = repo

    async def create(
        self,
        *,
        assignee_id: int,
        created_by_id: int,
        title: str,
        deadline: date | None,
        weekday: int | None,
        comment: str | None,
    ) -> Task:
        return await self._repo.create(
            assignee_id=assignee_id,
            created_by_id=created_by_id,
            title=title,
            deadline=deadline,
            weekday=weekday,
            comment=comment,
        )

    async def list_for_user(
        self,
        assignee_id: int,
        *,
        weekday: int | None = None,
        include_completed: bool = False,
    ) -> list[Task]:
        return await self._repo.list_for_user(
            assignee_id,
            weekday=weekday,
            include_completed=include_completed,
        )

    async def get_by_id(self, task_id: int) -> Task | None:
        return await self._repo.get_by_id(task_id)

    async def complete(self, task_id: int) -> Task | None:
        return await self._repo.complete(task_id)

    async def reopen(self, task_id: int) -> Task | None:
        return await self._repo.reopen(task_id)

    async def set_deadline(self, task_id: int, deadline: date | None, comment: str | None) -> Task | None:
        return await self._repo.set_deadline(task_id, deadline, comment)

    async def delete(self, task_id: int) -> Task | None:
        return await self._repo.delete(task_id)

    async def list_due_weekday(self, weekday: int, *, day: date) -> list[Task]:
        return await self._repo.list_due_weekday(weekday, day=day)

    async def mark_reminded(self, task_id: int, day: date) -> None:
        await self._repo.mark_reminded(task_id, day)

