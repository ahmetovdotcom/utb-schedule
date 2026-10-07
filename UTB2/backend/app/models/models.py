from typing import Optional, List
from sqlalchemy import JSON, BigInteger, SmallInteger, String, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship


from app.core.database import Base





class Group(Base):
    __tablename__ = "groups"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)

    # связи
    users: Mapped[List["User"]] = relationship(back_populates="group", cascade="all, delete-orphan")
    schedules: Mapped[List["Schedule"]] = relationship(back_populates="group", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)

    group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )

    # связи
    group: Mapped[Optional["Group"]] = relationship(back_populates="users")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    time: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    room: Mapped[str] = mapped_column(String(620), nullable=False)


    # relactionships
    group: Mapped["Group"] = relationship(back_populates="schedules")

class PublishedGroupLink(Base):
    """Stable mapping from the staff system to existing student group IDs."""
    __tablename__ = "published_group_links"
    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), unique=True)


class PublicationState(Base):
    __tablename__ = "publication_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(BigInteger)
    published_at: Mapped[str] = mapped_column(String(50))
    payload_hash: Mapped[str] = mapped_column(String(64))
    groups_count: Mapped[int]
    lessons_count: Mapped[int]


class PublishedTeacher(Base):
    __tablename__ = "published_teachers"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(512))
    lessons: Mapped[list] = mapped_column(JSON)


class ManualPublicationSource(Base):
    """Bind UTB2 to one manual-scheduler database after the first successful handover."""
    __tablename__ = "manual_publication_source"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
