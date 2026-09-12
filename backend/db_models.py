from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, UtcDateTime


class TeacherSettingsRecord(Base):
    __tablename__ = "teacher_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(100))


class AvailabilitySlotRecord(Base):
    __tablename__ = "availability_slots"
    __table_args__ = (
        CheckConstraint("weekday >= 1 AND weekday <= 5", name="weekday_range"),
        UniqueConstraint("weekday", "local_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, index=True)
    local_time: Mapped[str] = mapped_column(String(5))


class StudentRecord(Base):
    __tablename__ = "students"
    __table_args__ = (CheckConstraint("slot_day >= 1 AND slot_day <= 5", name="slot_day_range"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    slot_day: Mapped[int] = mapped_column(Integer)
    slot_time: Mapped[str] = mapped_column(String(5))


class PackageRecord(Base):
    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint("size IN (5, 8, 10)", name="valid_size"),
        CheckConstraint("used >= 0 AND used <= size", name="used_range"),
        UniqueConstraint("student_id", "period_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    size: Mapped[int] = mapped_column(Integer)
    used: Mapped[int] = mapped_column(Integer, default=0)
    period_no: Mapped[int] = mapped_column(Integer)
    invoice_sent: Mapped[bool] = mapped_column(Boolean, default=False)


class LessonRecord(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint("seq >= 1", name="positive_sequence"),
        UniqueConstraint("starts_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)


class BlackoutRecord(Base):
    __tablename__ = "blackouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starts_at: Mapped[datetime] = mapped_column(UtcDateTime, unique=True, index=True)
    note: Mapped[str] = mapped_column(String(500))
