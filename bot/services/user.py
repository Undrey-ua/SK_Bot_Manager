from __future__ import annotations

from database.models import User
from database.repositories.user import UserRepository


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self._repo.get_by_telegram_id(telegram_id)

    async def get_or_create(
        self,
        telegram_id: int,
        name: str,
    ) -> tuple[User, bool]:
        user = await self._repo.get_by_telegram_id(telegram_id)
        if user:
            return user, False
        user = await self._repo.create(telegram_id=telegram_id, name=name)
        return user, True

    async def list_all(self) -> list[User]:
        return await self._repo.list_all()
