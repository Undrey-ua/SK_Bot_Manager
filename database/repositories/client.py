from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Client
from database.repositories.base import BaseRepository


class ClientRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_manager(self, manager_id: int) -> list[Client]:
        result = await self._session.execute(
            select(Client)
            .where(Client.manager_id == manager_id)
            .order_by(Client.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, client_id: int) -> Client | None:
        result = await self._session.execute(
            select(Client).where(Client.id == client_id)
        )
        return result.scalar_one_or_none()
