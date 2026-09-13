from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
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
    """One package of lessons sold to a student.

    ``size`` is the number of lessons the package holds in total, not one of the
    three sizes on the price list. Renewing a package tops it up in place (#13),
    so a 10 that was renewed by 10 is a 20, and 5 + 8 + 5 is an 18 -- which is
    why the constraint is ``>= 1`` rather than the old ``IN (5, 8, 10)``. What
    is *purchasable* is still 5, 8 or 10; that lives in ``PackageRequest``.

    The trade-off, stated plainly: this keeps no record of what was sold when. A
    ``size`` of 20 is indistinguishable from 10 + 10 and from 8 + 8 + 4. An
    audit table was considered and rejected as too much schema for now; it can
    be added later without changing the API.
    """

    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint("size >= 1", name="valid_size"),
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


class LessonMoveRequestRecord(Base):
    """One request to move a lesson, kept after it is answered (#10).

    Resolving a request used to delete the row, so "a row exists" and "someone
    is waiting for an answer" were the same fact. A decline now keeps the row
    with ``status="declined"`` and an optional ``decline_reason``, so the
    student is told rather than watching the request vanish, and a request that
    goes stale on its own ends as ``status="expired"`` the same way.

    That makes the two unique indexes below **partial**, which is the whole
    trap this change has to avoid. Unscoped, they said "one row per lesson, one
    row per requested time, ever" -- true and harmless while resolving deleted
    the row, and a permanent block the moment it does not: a lesson's first
    decline would own that ``lesson_id`` forever and no later request could
    reuse it. Scoped to ``status = 'pending'``, a resolved row is inert history.

    ``status`` deliberately carries no index of its own. Every query that
    filters on it also filters on ``lesson_id`` or sweeps the whole table, and
    a table this small pays nothing for the scan.
    """

    __tablename__ = "lesson_move_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'declined', 'expired')", name="move_request_status"
        ),
        Index(
            "ix_lesson_move_requests_lesson_id",
            "lesson_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
        ),
        Index(
            "ix_lesson_move_requests_requested_starts_at",
            "requested_starts_at",
            unique=True,
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    requested_starts_at: Mapped[datetime] = mapped_column(UtcDateTime)
    status: Mapped[str] = mapped_column(String(20))
    decline_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class BlackoutRecord(Base):
    __tablename__ = "blackouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starts_at: Mapped[datetime] = mapped_column(UtcDateTime, unique=True, index=True)
    note: Mapped[str] = mapped_column(String(500))


class StudentPauseRecord(Base):
    """One break a student took, stored as the dates it covers.

    `weeks` is kept for the record and for display, but nothing is computed from
    it at read time: `starts_on` and `ends_on` are what the store queries, so a
    pause can be asserted on and shown without re-deriving it from a duration.
    The break covers `[starts_on, ends_on)` -- on `ends_on` the student is back.

    `ended_early_at` is what separates the two ways a pause can end: null means
    it ran its course and expired on `ends_on`, a timestamp means the teacher or
    the student ended it before that.
    """

    __tablename__ = "student_pauses"
    __table_args__ = (CheckConstraint("weeks >= 1 AND weeks <= 6", name="pause_weeks_range"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    weeks: Mapped[int] = mapped_column(Integer)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    ended_early_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
