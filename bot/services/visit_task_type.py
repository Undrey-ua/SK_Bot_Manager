from __future__ import annotations

from database.models import VisitTaskType
from database.repositories.visit_task_type import VisitTaskTypeRepository


class VisitTaskTypeService:
    def __init__(self, repo: VisitTaskTypeRepository) -> None:
        self._repo = repo

    async def list_active(self) -> list[VisitTaskType]:
        return await self._repo.list_active()

    async def filter_known_tasks(self, codes: list[str]) -> list[str]:
        active = {row.code for row in await self._repo.list_active()}
        return [code for code in codes if code in active]
