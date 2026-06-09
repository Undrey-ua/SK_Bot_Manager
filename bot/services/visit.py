from __future__ import annotations

from database.models import Visit
from database.repositories.visit import VisitRepository


class VisitService:
    def __init__(self, repo: VisitRepository) -> None:
        self._repo = repo

    async def create_visit(
        self,
        manager_id: int,
        client_id: int,
        visit_type: str,
        comment: str | None,
        tasks: list[str],
        photo_urls: list[str],
    ) -> Visit:
        return await self._repo.create(
            manager_id=manager_id,
            client_id=client_id,
            visit_type=visit_type,
            comment=comment,
            tasks=tasks,
            photo_urls=photo_urls,
        )
