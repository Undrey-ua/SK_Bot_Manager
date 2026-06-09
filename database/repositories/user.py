from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config.team import filter_regional_managers
from database.models import (
    Client,
    ManagerRegion,
    Reserve,
    Sale,
    StandTransfer,
    Task,
    User,
    UserRole,
    Visit,
)
from database.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def list_regional_managers(self) -> list[User]:
        return filter_regional_managers(await self.list_all())

    async def list_all(self) -> list[User]:
        result = await self._session.execute(
            select(User)
            .options(selectinload(User.supervisor))
            .order_by(User.name)
        )
        return list(result.scalars().all())

    async def count_by_role(self, role: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(User).where(User.role == role)
        )
        return int(result.scalar_one())

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self._session.execute(
            select(User)
            .options(selectinload(User.supervisor))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def count_supervisees(self, supervisor_id: int) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(User)
            .where(User.supervisor_id == supervisor_id)
        )
        return int(result.scalar_one())

    async def related_usage_counts(self, user_id: int) -> dict[str, int]:
        async def _count(model, column) -> int:
            result = await self._session.execute(
                select(func.count()).select_from(model).where(column == user_id)
            )
            return int(result.scalar_one())

        tasks_assignee = await _count(Task, Task.assignee_id)
        tasks_created = await _count(Task, Task.created_by_id)
        return {
            "clients": await _count(Client, Client.manager_id),
            "visits": await _count(Visit, Visit.manager_id),
            "sales": await _count(Sale, Sale.manager_id),
            "reserves": await _count(Reserve, Reserve.manager_id),
            "regions": await _count(ManagerRegion, ManagerRegion.manager_id),
            "stand_transfers": await _count(StandTransfer, StandTransfer.manager_id),
            "tasks": tasks_assignee + tasks_created,
            "supervisees": await self.count_supervisees(user_id),
        }

    async def update(
        self,
        user: User,
        *,
        name: str,
        telegram_id: int,
        role: str,
        supervisor_id: int | None,
    ) -> User:
        user.name = name.strip()
        user.telegram_id = telegram_id
        user.role = role
        user.supervisor_id = (
            supervisor_id if role == UserRole.SALES_MANAGER.value else None
        )
        await self._session.flush()
        return user

    async def delete(self, user: User) -> None:
        await self._session.execute(delete(User).where(User.id == user.id))

    async def create(
        self,
        telegram_id: int,
        name: str,
        role: str = UserRole.MANAGER.value,
        *,
        supervisor_id: int | None = None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            name=name.strip(),
            role=role,
            supervisor_id=supervisor_id,
        )
        self._session.add(user)
        await self._session.flush()
        return user
