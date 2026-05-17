from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession

from bot.services.client import ClientService
from bot.services.storage import StorageService
from bot.services.user import UserService
from bot.services.visit import VisitService
from config.settings import Settings, get_settings
from database.repositories.client import ClientRepository
from database.repositories.user import UserRepository
from database.repositories.visit import VisitRepository
from database.session import create_engine, create_session_factory


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    storage_service: StorageService

    def user_service(self, session: AsyncSession) -> UserService:
        return UserService(UserRepository(session))

    def client_service(self, session: AsyncSession) -> ClientService:
        return ClientService(ClientRepository(session))

    def visit_service(self, session: AsyncSession) -> VisitService:
        return VisitService(VisitRepository(session))


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    engine = create_engine(settings.database_url)
    return Container(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        storage_service=StorageService(settings),
    )
