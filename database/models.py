from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRole(StrEnum):
    MANAGER = "manager"
    ADMIN = "admin"


class VisitType(StrEnum):
    PVH = "pvh"
    STAND = "stand"


class TaskType(StrEnum):
    STAND_CONTROL = "stand_control"
    PHOTO = "photo"
    ORDER = "order"
    PRICE_CONTROL = "price_control"
    SELLER_TRAINING = "seller_training"


TASK_LABELS: dict[TaskType, str] = {
    TaskType.STAND_CONTROL: "Контроль стенду",
    TaskType.PHOTO: "Фото",
    TaskType.ORDER: "Замовлення",
    TaskType.PRICE_CONTROL: "Контроль цін",
    TaskType.SELLER_TRAINING: "Навчання продавця",
}

VISIT_TYPE_LABELS: dict[VisitType, str] = {
    VisitType.PVH: "ПВХ",
    VisitType.STAND: "Стенд",
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default=UserRole.MANAGER)

    clients: Mapped[list["Client"]] = relationship(back_populates="manager")
    visits: Mapped[list["Visit"]] = relationship(back_populates="manager")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    manager: Mapped["User"] = relationship(back_populates="clients")
    visits: Mapped[list["Visit"]] = relationship(back_populates="client")


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    visit_type: Mapped[str] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class VisitPhoto(Base):
    __tablename__ = "visit_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), index=True)
    photo_url: Mapped[str] = mapped_column(String(1000))

    visit: Mapped["Visit"] = relationship(back_populates="photos")
