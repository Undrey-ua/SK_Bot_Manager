from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Visit, VisitPhoto, VisitTask
from database.repositories.base import BaseRepository


class VisitRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        manager_id: int,
        client_id: int,
        visit_type: str,
        comment: str | None,
        tasks: list[str],
        photo_urls: list[str],
    ) -> Visit:
        visit = Visit(
            manager_id=manager_id,
            client_id=client_id,
            visit_type=visit_type,
            comment=comment,
        )
        self._session.add(visit)
        await self._session.flush()

        for task in tasks:
            self._session.add(VisitTask(visit_id=visit.id, task=task))

        for url in photo_urls:
            self._session.add(VisitPhoto(visit_id=visit.id, photo_url=url))

        await self._session.flush()
        return visit
