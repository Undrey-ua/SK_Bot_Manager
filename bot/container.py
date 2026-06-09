from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession

from bot.services.brand import BrandService
from bot.services.client import ClientService
from bot.services.region import RegionService
from bot.services.sale import SaleService
from bot.services.reserve import ReserveService
from bot.services.stand import StandService
from bot.services.storage import StorageService
from bot.services.task import TaskService
from bot.services.user import UserService
from bot.services.visit import VisitService
from bot.services.visit_task_type import VisitTaskTypeService
from config.settings import Settings, get_settings
from database.repositories.brand import BrandRepository
from database.repositories.client import ClientRepository
from database.repositories.region import RegionRepository
from database.repositories.reserve import ReserveRepository
from database.repositories.sale import SaleRepository
from database.repositories.stand import StandRepository
from database.repositories.task import TaskRepository
from database.repositories.user import UserRepository
from database.repositories.visit import VisitRepository
from database.repositories.visit_task_type import VisitTaskTypeRepository
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

    def region_service(self, session: AsyncSession) -> RegionService:
        return RegionService(RegionRepository(session))

    def stand_service(self, session: AsyncSession) -> StandService:
        return StandService(StandRepository(session))

    def visit_service(self, session: AsyncSession) -> VisitService:
        return VisitService(VisitRepository(session))

    def brand_service(self, session: AsyncSession) -> BrandService:
        return BrandService(BrandRepository(session))

    def sale_service(self, session: AsyncSession) -> SaleService:
        return SaleService(SaleRepository(session))

    def reserve_service(self, session: AsyncSession) -> ReserveService:
        return ReserveService(ReserveRepository(session))

    def task_service(self, session: AsyncSession) -> TaskService:
        return TaskService(TaskRepository(session))

    def visit_task_type_service(self, session: AsyncSession) -> VisitTaskTypeService:
        return VisitTaskTypeService(VisitTaskTypeRepository(session))


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    engine = create_engine(settings.database_url)
    return Container(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        storage_service=StorageService(settings),
    )
