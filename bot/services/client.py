from database.models import Client
from database.repositories.client import ClientRepository


class ClientService:
    def __init__(self, repo: ClientRepository) -> None:
        self._repo = repo

    async def list_by_manager(self, manager_id: int) -> list[Client]:
        return await self._repo.list_by_manager(manager_id)

    async def get_by_id(self, client_id: int) -> Client | None:
        return await self._repo.get_by_id(client_id)
