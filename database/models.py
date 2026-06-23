from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRole(str, Enum):
    """admin — один; leader — керівники; manager — регіональні; sales_manager — збут."""

    MANAGER = "manager"
    ADMIN = "admin"
    LEADER = "leader"
    SALES_MANAGER = "sales_manager"


class VisitType(str, Enum):
    PVH = "pvh"
    STAND = "stand"


class TaskType(str, Enum):
    STAND_CONTROL = "stand_control"
    PHOTO = "photo"
    ORDER = "order"
    PRICE_CONTROL = "price_control"
    SELLER_TRAINING = "seller_training"
    NEW_PRODUCTS = "new_products"
    INKASSATION = "inkassation"


TASK_LABELS: dict[TaskType, str] = {
    TaskType.STAND_CONTROL: "Контроль стенду",
    TaskType.PHOTO: "Фото",
    TaskType.ORDER: "Замовлення",
    TaskType.PRICE_CONTROL: "Контроль цін",
    TaskType.SELLER_TRAINING: "Навчання продавця",
    TaskType.NEW_PRODUCTS: "Презентація новинок",
    TaskType.INKASSATION: "Інкасація",
}

VISIT_TYPE_LABELS: dict[VisitType, str] = {
    VisitType.PVH: "ПВХ",
    VisitType.STAND: "Стенд",
}


class ManagerTaskKind(str, Enum):
    """Тип призначеної задачі (веб / бот — не плутати з TaskType візитів)."""

    GENERAL = "general"
    STAND_INSTALL = "stand_install"
    STAND_MOVE = "stand_move"
    DOCUMENTS = "documents"


MANAGER_TASK_KIND_LABELS: dict[ManagerTaskKind, str] = {
    ManagerTaskKind.GENERAL: "Загальна",
    ManagerTaskKind.STAND_INSTALL: "Установка стендів",
    ManagerTaskKind.STAND_MOVE: "Переміщення стендів",
    ManagerTaskKind.DOCUMENTS: "Документообіг",
}

MANAGER_TASK_KIND_DEFAULT = ManagerTaskKind.GENERAL.value


def normalize_manager_task_kind(kind: str | None) -> str:
    if not kind:
        return MANAGER_TASK_KIND_DEFAULT
    try:
        return ManagerTaskKind(kind).value
    except ValueError:
        return MANAGER_TASK_KIND_DEFAULT


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default=UserRole.MANAGER)
    supervisor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    supervisor: Mapped[Optional["User"]] = relationship(
        remote_side="User.id",
        foreign_keys=[supervisor_id],
    )
    clients: Mapped[list["Client"]] = relationship(back_populates="manager")
    visits: Mapped[list["Visit"]] = relationship(back_populates="manager")
    sales: Mapped[list["Sale"]] = relationship(back_populates="manager")
    reserves: Mapped[list["Reserve"]] = relationship(
        back_populates="manager",
        foreign_keys="Reserve.manager_id",
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="assignee",
        foreign_keys="Task.assignee_id",
    )
    regions: Mapped[list["ManagerRegion"]] = relationship(back_populates="manager")


class ManagerRegion(Base):
    __tablename__ = "manager_regions"
    __table_args__ = (UniqueConstraint("manager_id", "name", name="uq_manager_region"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))

    manager: Mapped["User"] = relationship(back_populates="regions")
    clients: Mapped[list["Client"]] = relationship(back_populates="region")


class Stand(Base):
    __tablename__ = "stands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    client_links: Mapped[list["ClientStand"]] = relationship(back_populates="stand")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("manager_regions.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(String(500))
    city: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    contacts: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    manager: Mapped["User"] = relationship(back_populates="clients")
    region: Mapped["ManagerRegion"] = relationship(back_populates="clients")
    visits: Mapped[list["Visit"]] = relationship(back_populates="client")
    stand_links: Mapped[list["ClientStand"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )
    swatch_links: Mapped[list["ClientSwatch"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )
    sales: Mapped[list["Sale"]] = relationship(back_populates="client")


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    sales: Mapped[list["Sale"]] = relationship(back_populates="brand")
    swatch_links: Mapped[list["ClientSwatch"]] = relationship(back_populates="brand")


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sold_at: Mapped[date] = mapped_column(Date, index=True)
    from_swatch: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    manager: Mapped["User"] = relationship(back_populates="sales")
    client: Mapped["Client"] = relationship(back_populates="sales")
    brand: Mapped["Brand"] = relationship(back_populates="sales")


class Reserve(Base):
    __tablename__ = "reserves"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    region_id: Mapped[int] = mapped_column(ForeignKey("manager_regions.id"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)

    material: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    extended_count: Mapped[int] = mapped_column(default=0)

    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    manager: Mapped["User"] = relationship(
        back_populates="reserves",
        foreign_keys=[manager_id],
    )
    created_by: Mapped[Optional["User"]] = relationship(foreign_keys=[created_by_id])
    region: Mapped["ManagerRegion"] = relationship()
    client: Mapped["Client"] = relationship()


class ManagerSalesPlan(Base):
    __tablename__ = "manager_sales_plans"
    __table_args__ = (
        UniqueConstraint("manager_id", "year", "month", name="uq_manager_sales_plan_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    year: Mapped[int] = mapped_column(index=True)
    month: Mapped[int] = mapped_column(index=True)
    target_sqm: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    manager: Mapped["User"] = relationship(foreign_keys=[manager_id])
    created_by: Mapped[Optional["User"]] = relationship(foreign_keys=[created_by_id])


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    title: Mapped[str] = mapped_column(String(300))
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(
        String(32),
        default=MANAGER_TASK_KIND_DEFAULT,
        server_default=MANAGER_TASK_KIND_DEFAULT,
        index=True,
    )

    deadline: Mapped[Optional[date]] = mapped_column(Date, index=True, nullable=True)
    weekday: Mapped[Optional[int]] = mapped_column(nullable=True)  # 0=Mon ... 6=Sun

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    reminder_sent_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    assignee: Mapped["User"] = relationship(
        back_populates="tasks",
        foreign_keys=[assignee_id],
    )
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])

class ClientStand(Base):
    __tablename__ = "client_stands"
    __table_args__ = (UniqueConstraint("client_id", "stand_id", name="uq_client_stand"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    stand_id: Mapped[int] = mapped_column(ForeignKey("stands.id"), index=True)
    quantity: Mapped[int] = mapped_column(default=1)

    client: Mapped["Client"] = relationship(back_populates="stand_links")
    stand: Mapped["Stand"] = relationship(back_populates="client_links")


class ClientSwatch(Base):
    __tablename__ = "client_swatches"
    __table_args__ = (UniqueConstraint("client_id", "brand_id", name="uq_client_swatch"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), index=True)

    client: Mapped["Client"] = relationship(back_populates="swatch_links")
    brand: Mapped["Brand"] = relationship(back_populates="swatch_links")


class ManagerStandStock(Base):
    __tablename__ = "manager_stand_stock"
    __table_args__ = (
        UniqueConstraint("manager_id", "stand_id", name="uq_manager_stand_stock"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    stand_id: Mapped[int] = mapped_column(ForeignKey("stands.id"), index=True)
    quantity: Mapped[int] = mapped_column(default=0)

    manager: Mapped["User"] = relationship(foreign_keys=[manager_id])
    stand: Mapped["Stand"] = relationship()


class StandTransferOperation(str, Enum):
    MOVE = "move"
    WRITE_OFF = "write_off"
    ALLOCATE = "allocate"
    TO_WAREHOUSE = "to_warehouse"
    FROM_WAREHOUSE = "from_warehouse"


STAND_TRANSFER_OPERATION_LABELS: dict[str, str] = {
    StandTransferOperation.MOVE.value: "Переміщення",
    StandTransferOperation.WRITE_OFF.value: "Списання",
    StandTransferOperation.ALLOCATE.value: "Виділення на склад",
    StandTransferOperation.TO_WAREHOUSE.value: "На склад",
    StandTransferOperation.FROM_WAREHOUSE.value: "Зі складу",
}

WAREHOUSE_LOCATION_LABEL = "Віртуальний склад"
ALLOCATE_SOURCE_LABEL = "Виділення керівником"


class StandTransfer(Base):
    __tablename__ = "stand_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    from_client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clients.id"),
        index=True,
        nullable=True,
    )
    to_client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clients.id"),
        index=True,
        nullable=True,
    )
    stand_id: Mapped[int] = mapped_column(ForeignKey("stands.id"), index=True)
    quantity: Mapped[int] = mapped_column(default=1)
    operation: Mapped[str] = mapped_column(
        String(20),
        default=StandTransferOperation.MOVE.value,
        server_default=StandTransferOperation.MOVE.value,
    )
    to_was_new: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    manager: Mapped["User"] = relationship(foreign_keys=[manager_id])
    from_client: Mapped[Optional["Client"]] = relationship(foreign_keys=[from_client_id])
    to_client: Mapped["Client"] = relationship(foreign_keys=[to_client_id])
    stand: Mapped["Stand"] = relationship()


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    visit_type: Mapped[str] = mapped_column(String(50))
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    manager: Mapped["User"] = relationship(back_populates="visits")
    client: Mapped["Client"] = relationship(back_populates="visits")
    tasks: Mapped[list["VisitTask"]] = relationship(
        back_populates="visit",
        cascade="all, delete-orphan",
    )
    photos: Mapped[list["VisitPhoto"]] = relationship(
        back_populates="visit",
        cascade="all, delete-orphan",
    )


class VisitTask(Base):
    __tablename__ = "visit_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), index=True)
    task: Mapped[str] = mapped_column(String(50))

    visit: Mapped["Visit"] = relationship(back_populates="tasks")


class VisitTaskType(Base):
    __tablename__ = "visit_task_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    label: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class VisitPhoto(Base):
    __tablename__ = "visit_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), index=True)
    photo_url: Mapped[str] = mapped_column(String(1000))

    visit: Mapped["Visit"] = relationship(back_populates="photos")
