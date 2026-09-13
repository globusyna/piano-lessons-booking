from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from threading import RLock
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import hash_password
from .database import Base, create_database_engine, create_session_factory
from .db_models import (
    AvailabilitySlotRecord,
    BlackoutRecord,
    LessonMoveRequestRecord,
    LessonRecord,
    PackageRecord,
    StudentPauseRecord,
    StudentRecord,
    TeacherSettingsRecord,
)
from .migrator import downgrade_to_base, upgrade_to_head
from .models import (
    Blackout,
    Lesson,
    LessonMoveRequest,
    LessonStatus,
    Package,
    Student,
    StudentStatus,
)


STUDIO_TZ = ZoneInfo("Europe/Oslo")
ROW_TIMES = ["14:00", "14:45", "15:30", "16:15", "17:00", "17:45", "18:30"]


class StudioClock:
    """The one "now" the catch-up-on-read logic reads.

    Two behaviours in the store have to be driven from a test at an exact
    instant -- the moment a package's last lesson passes (#9), and the moment a
    student's break runs out (#12) -- and a test cannot wait for either instant
    to arrive. So both code paths ask this object for the time instead of
    calling ``datetime.now`` inline, and a test pins it:

        with clock.pinned(last_lesson_starts_at):
            client.get("/admin/alerts", headers=admin_headers)

    Deliberately narrow: only the two catch-up paths read it today. Giving the
    whole backend a controllable clock is #32 (B-51), and this seam is meant to
    be what that issue grows, not something it has to undo.
    """

    def __init__(self) -> None:
        self._pinned: datetime | None = None

    def now(self) -> datetime:
        """The authoritative "now", in studio time."""
        pinned = self._pinned
        return (pinned if pinned is not None else datetime.now(STUDIO_TZ)).astimezone(STUDIO_TZ)

    @contextmanager
    def pinned(self, instant: datetime) -> Iterator[datetime]:
        """Freeze ``now`` at ``instant`` for the duration of the block."""
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("A pinned instant must carry a UTC offset")
        previous = self._pinned
        self._pinned = instant
        try:
            yield self.now()
        finally:
            self._pinned = previous


clock = StudioClock()


class StoreError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class DatabaseStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.engine = create_database_engine(database_url)
        self._sessions = create_session_factory(self.engine)
        self._lock = RLock()
        # Migrations, not create_all: an existing database has to be changed, not
        # just filled in. They run on this engine's own connection because the
        # test suite's in-memory database exists only inside it.
        upgrade_to_head(self.engine)
        self._seed_if_empty()

    @property
    def admin_username(self) -> str:
        with self._sessions() as session:
            return self._teacher(session).username

    @property
    def admin_password_hash(self) -> str:
        with self._sessions() as session:
            return self._teacher(session).password_hash

    @property
    def students(self) -> dict[int, Student]:
        with self._sessions() as session:
            records = session.scalars(select(StudentRecord).order_by(StudentRecord.id)).all()
            return {record.id: self._student_model(session, record) for record in records}

    @property
    def lessons(self) -> dict[int, Lesson]:
        with self._sessions() as session:
            records = session.scalars(select(LessonRecord)).all()
            return {record.id: self._lesson_model(record) for record in records}

    @property
    def blackouts(self) -> dict[int, Blackout]:
        with self._sessions() as session:
            records = session.scalars(select(BlackoutRecord)).all()
            return {record.id: self._blackout_model(record) for record in records}

    @property
    def hours(self) -> dict[int, list[str]]:
        with self._sessions() as session:
            records = session.scalars(
                select(AvailabilitySlotRecord).order_by(
                    AvailabilitySlotRecord.weekday, AvailabilitySlotRecord.local_time
                )
            ).all()
            result: dict[int, list[str]] = {day: [] for day in range(1, 6)}
            for record in records:
                result[record.weekday].append(record.local_time)
            return result

    def reset(self) -> None:
        with self._lock:
            self._discard_every_row()
            downgrade_to_base(self.engine)
            upgrade_to_head(self.engine)
            self._seed_if_empty()

    def _discard_every_row(self) -> None:
        """Empty every table before the schema is unwound.

        `reset` throws the whole database away and reseeds it, so by the time
        the downgrades run there is nothing left worth protecting -- but a
        downgrade cannot know that from the inside. `ac812725de6c` refuses to
        run while a package has been topped up past the old price list, because
        it will not invent a size for it (#13). That guard is right for someone
        rolling a real database back and wrong as a way of stopping a test
        wiping its own fixture, so the rows go first and the downgrade runs over
        an empty database.

        Deleting rather than dropping keeps `reset` on the migration path: every
        test still exercises a full downgrade-to-base and upgrade-to-head, which
        is what #15 built it out of and what makes a broken revision show up in
        the suite rather than in production.

        Children first -- `sorted_tables` is dependency order, so reversing it
        clears a table before whatever it points at. `alembic_version` is not on
        `Base.metadata` and is deliberately left alone: the downgrade needs it.
        """
        with self._sessions.begin() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(delete(table))

    def _seed_if_empty(self) -> None:
        with self._sessions.begin() as session:
            if session.scalar(select(func.count()).select_from(TeacherSettingsRecord)):
                return
            session.add(
                TeacherSettingsRecord(
                    id=1,
                    username="admin",
                    password_hash=hash_password("piano"),
                    timezone=STUDIO_TZ.key,
                )
            )
            seeded_hours = {
                1: ROW_TIMES[1:],
                2: ROW_TIMES[:],
                3: ROW_TIMES[:-1],
                4: ROW_TIMES[:],
                5: ROW_TIMES[:-2],
            }
            session.add_all(
                AvailabilitySlotRecord(weekday=day, local_time=slot_time)
                for day, times in seeded_hours.items()
                for slot_time in times
            )
            seeds = [
                ("Anna Lie", "anna", StudentStatus.ACTIVE, 2, "16:15", 10, 7, 3),
                ("Jonas Berg", "jonas", StudentStatus.ACTIVE, 1, "15:30", 10, 10, 2),
                ("Mira Solheim", "mira", StudentStatus.PAUSED, 3, "17:00", 8, 4, 1),
                ("Teodor Haugen", "teodor", StudentStatus.FLAGGED, 4, "14:45", 10, 3, 5),
                ("Selma Ruud", "selma", StudentStatus.ACTIVE, 5, "17:45", 10, 2, 1),
                ("Oskar Dahl", "oskar", StudentStatus.ACTIVE, 2, "18:30", 10, 9, 4),
            ]
            monday = self._monday(datetime.now(STUDIO_TZ).date())
            for student_id, seed in enumerate(seeds, start=1):
                name, token, status, day, slot_time, size, used, period = seed
                student = StudentRecord(
                    id=student_id,
                    name=name,
                    status=status.value,
                    token=token,
                    slot_day=day,
                    slot_time=slot_time,
                )
                session.add(student)
                session.flush()
                package = PackageRecord(
                    student_id=student.id,
                    size=size,
                    used=used,
                    period_no=period,
                    invoice_sent=False,
                )
                session.add(package)
                session.flush()
                for seq in range(1, used + 1):
                    lesson_day = monday + timedelta(days=day - 1, weeks=seq - used - 1)
                    self._add_lesson_record(
                        session,
                        student.id,
                        package.id,
                        seq,
                        self._at(lesson_day, slot_time),
                        LessonStatus.DONE,
                    )
                for seq in range(used + 1, size + 1):
                    lesson_day = monday + timedelta(days=day - 1, weeks=seq - used - 1)
                    self._add_lesson_record(
                        session, student.id, package.id, seq, self._at(lesson_day, slot_time)
                    )
            session.add_all(
                [
                    BlackoutRecord(
                        starts_at=self._at(monday + timedelta(days=2), "17:00"), note="Dentist"
                    ),
                    BlackoutRecord(
                        starts_at=self._at(monday + timedelta(days=2), "17:45"), note="Dentist"
                    ),
                    BlackoutRecord(
                        starts_at=self._at(monday + timedelta(days=9), "14:00"),
                        note="Recital rehearsal",
                    ),
                ]
            )

    @staticmethod
    def _monday(value: date) -> date:
        return value - timedelta(days=value.weekday())

    @staticmethod
    def _at(value: date, local_time: str) -> datetime:
        hour, minute = map(int, local_time.split(":"))
        return datetime.combine(value, time(hour, minute), STUDIO_TZ)

    @staticmethod
    def _studio(value: datetime) -> datetime:
        return value.astimezone(STUDIO_TZ)

    @staticmethod
    def _teacher(session: Session) -> TeacherSettingsRecord:
        record = session.scalar(select(TeacherSettingsRecord).limit(1))
        if record is None:
            raise RuntimeError("Teacher settings have not been initialized")
        return record

    @staticmethod
    def _current_package(session: Session, student_id: int) -> PackageRecord:
        record = session.scalar(
            select(PackageRecord)
            .where(PackageRecord.student_id == student_id)
            .order_by(PackageRecord.period_no.desc(), PackageRecord.id.desc())
            .limit(1)
        )
        if record is None:
            raise RuntimeError(f"Student {student_id} has no package")
        return record

    def _student_model(self, session: Session, record: StudentRecord) -> Student:
        package = self._current_package(session, record.id)
        return Student(
            id=record.id,
            name=record.name,
            status=StudentStatus(record.status),
            pausedUntil=self._paused_until(session, record),
            token=record.token,
            slotDay=record.slot_day,
            slotTime=record.slot_time,
            pkg=Package(
                id=package.id,
                size=package.size,
                used=package.used,
                periodNo=package.period_no,
            ),
            invoiceSent=package.invoice_sent,
        )

    def _lesson_model(self, record: LessonRecord) -> Lesson:
        return Lesson(
            id=record.id,
            seq=record.seq,
            studentId=record.student_id,
            startsAt=self._studio(record.starts_at),
            status=LessonStatus(record.status),
        )

    def _blackout_model(self, record: BlackoutRecord) -> Blackout:
        return Blackout(id=record.id, startsAt=self._studio(record.starts_at), note=record.note)

    def _move_request_model(self, record: LessonMoveRequestRecord) -> LessonMoveRequest:
        return LessonMoveRequest(
            id=record.id,
            lessonId=record.lesson_id,
            requestedStartsAt=self._studio(record.requested_starts_at),
        )

    @staticmethod
    def _student_record(session: Session, student_id: int) -> StudentRecord:
        record = session.get(StudentRecord, student_id)
        if record is None:
            raise StoreError(404, "NOT_FOUND", "Student not found.")
        return record

    @staticmethod
    def _student_for_token_record(session: Session, token: str) -> StudentRecord:
        record = session.scalar(select(StudentRecord).where(StudentRecord.token == token))
        if record is None:
            raise StoreError(
                404, "INVALID_TOKEN", "This link isn't valid. Ask your teacher for a new one."
            )
        return record

    @staticmethod
    def _add_lesson_record(
        session: Session,
        student_id: int,
        package_id: int,
        seq: int,
        starts_at: datetime,
        status: LessonStatus = LessonStatus.SCHEDULED,
    ) -> LessonRecord:
        record = LessonRecord(
            student_id=student_id,
            package_id=package_id,
            seq=seq,
            starts_at=starts_at,
            status=status.value,
        )
        session.add(record)
        return record

    def student_for_token(self, token: str) -> Student:
        with self._sessions() as session:
            return self._student_model(session, self._student_for_token_record(session, token))

    def student(self, student_id: int) -> Student:
        with self._sessions() as session:
            return self._student_model(session, self._student_record(session, student_id))

    def list_students(self) -> list[Student]:
        return list(self.students.values())

    def lesson(self, lesson_id: int) -> Lesson | None:
        with self._sessions() as session:
            record = session.get(LessonRecord, lesson_id)
            return self._lesson_model(record) if record else None

    def lesson_history(self, student_id: int) -> list[Lesson]:
        with self._sessions() as session:
            self._student_record(session, student_id)
            records = session.scalars(
                select(LessonRecord)
                .where(LessonRecord.student_id == student_id)
                .order_by(LessonRecord.starts_at)
            ).all()
            return [self._lesson_model(record) for record in records]

    def scheduled_lesson_at(self, starts_at: datetime) -> Lesson | None:
        with self._sessions() as session:
            record = session.scalar(
                select(LessonRecord).where(
                    LessonRecord.starts_at == starts_at,
                    LessonRecord.status == LessonStatus.SCHEDULED.value,
                )
            )
            return self._lesson_model(record) if record else None

    def move_request_for_lesson(self, lesson_id: int) -> LessonMoveRequest | None:
        with self._sessions() as session:
            record = session.scalar(
                select(LessonMoveRequestRecord).where(
                    LessonMoveRequestRecord.lesson_id == lesson_id
                )
            )
            return self._move_request_model(record) if record else None

    def blackout_at(self, starts_at: datetime) -> Blackout | None:
        with self._sessions() as session:
            record = session.scalar(
                select(BlackoutRecord).where(BlackoutRecord.starts_at == starts_at)
            )
            return self._blackout_model(record) if record else None

    def list_blackouts(self) -> list[Blackout]:
        with self._sessions() as session:
            records = session.scalars(
                select(BlackoutRecord).order_by(BlackoutRecord.starts_at)
            ).all()
            return [self._blackout_model(record) for record in records]

    def is_day_locked(self, starts_at: datetime) -> bool:
        return starts_at.astimezone(STUDIO_TZ).date() < datetime.now(STUDIO_TZ).date()

    def can_request_lesson_move(self, starts_at: datetime) -> bool:
        return starts_at.astimezone(STUDIO_TZ) >= datetime.now(STUDIO_TZ) + timedelta(hours=48)

    def in_move_window(self, starts_at: datetime) -> bool:
        local = starts_at.astimezone(STUDIO_TZ)
        today = datetime.now(STUDIO_TZ).date()
        return (
            local > datetime.now(STUDIO_TZ)
            and today <= local.date() <= today + timedelta(days=21)
        )

    def _open_slots(
        self,
        session: Session,
        from_date: date,
        to_date: date,
        exclude_lesson_id: int | None = None,
        exclude_move_request_id: int | None = None,
    ) -> list[datetime]:
        if from_date > to_date:
            raise StoreError(
                400, "INVALID_RANGE", "The start date must be on or before the end date."
            )
        today = datetime.now(STUDIO_TZ).date()
        first, last = max(from_date, today), min(to_date, today + timedelta(days=21))
        if first > last:
            return []
        lesson_query = select(LessonRecord).where(
            LessonRecord.status == LessonStatus.SCHEDULED.value
        )
        if exclude_lesson_id is not None:
            lesson_query = lesson_query.where(LessonRecord.id != exclude_lesson_id)
        taken = {self._studio(record.starts_at) for record in session.scalars(lesson_query)}
        move_request_query = select(LessonMoveRequestRecord)
        if exclude_move_request_id is not None:
            move_request_query = move_request_query.where(
                LessonMoveRequestRecord.id != exclude_move_request_id
            )
        taken.update(
            self._studio(record.requested_starts_at)
            for record in session.scalars(move_request_query)
        )
        blocked = {
            self._studio(record.starts_at) for record in session.scalars(select(BlackoutRecord))
        }
        availability: dict[int, list[str]] = {day: [] for day in range(1, 6)}
        availability_records = session.scalars(
            select(AvailabilitySlotRecord).order_by(
                AvailabilitySlotRecord.weekday, AvailabilitySlotRecord.local_time
            )
        )
        for record in availability_records:
            availability[record.weekday].append(record.local_time)
        slots: list[datetime] = []
        current = first
        while current <= last:
            for slot_time in availability.get(current.isoweekday(), []):
                candidate = self._at(current, slot_time)
                if (
                    candidate not in taken
                    and candidate not in blocked
                    and self.in_move_window(candidate)
                ):
                    slots.append(candidate)
            current += timedelta(days=1)
        return sorted(slots)

    def open_slots(
        self, from_date: date, to_date: date, exclude_lesson_id: int | None = None
    ) -> list[datetime]:
        with self._sessions() as session:
            return self._open_slots(session, from_date, to_date, exclude_lesson_id)

    def request_lesson_move(
        self, token: str, lesson_id: int, starts_at: datetime
    ) -> LessonMoveRequest:
        try:
            with self._lock, self._sessions.begin() as session:
                student = self._student_for_token_record(session, token)
                lesson = session.get(LessonRecord, lesson_id)
                if lesson is None or lesson.student_id != student.id:
                    raise StoreError(
                        404,
                        "INVALID_TOKEN",
                        "This link isn't valid. Ask your teacher for a new one.",
                    )
                if lesson.status != LessonStatus.SCHEDULED.value:
                    raise StoreError(403, "LESSON_NOT_MOVABLE", "That lesson cannot be moved.")
                if student.status == StudentStatus.PAUSED.value:
                    raise StoreError(
                        403,
                        "STUDENT_PAUSED",
                        "Your lessons are paused. Your teacher will be in touch.",
                    )
                if student.status == StudentStatus.FLAGGED.value:
                    raise StoreError(
                        403,
                        "STUDENT_FLAGGED",
                        "There's an open question on your account. Your teacher will be in touch.",
                    )
                if not self.can_request_lesson_move(lesson.starts_at):
                    raise StoreError(
                        403,
                        "MOVE_NOTICE_REQUIRED",
                        "Lessons cannot be moved less than 48 hours before they start.",
                    )
                pending = session.scalar(
                    select(LessonMoveRequestRecord).where(
                        LessonMoveRequestRecord.lesson_id == lesson.id
                    )
                )
                if pending is not None:
                    raise StoreError(
                        409,
                        "MOVE_ALREADY_REQUESTED",
                        "A move request is already waiting for Andrea's approval.",
                    )
                if not self.in_move_window(starts_at):
                    raise StoreError(
                        400, "OUTSIDE_WINDOW", "That time is outside the booking window."
                    )
                available = self._open_slots(
                    session,
                    starts_at.astimezone(STUDIO_TZ).date(),
                    starts_at.astimezone(STUDIO_TZ).date(),
                    lesson.id,
                )
                if starts_at not in available:
                    raise StoreError(
                        409,
                        "SLOT_TAKEN",
                        "Someone just took that time. Here are the times still open.",
                    )
                request = LessonMoveRequestRecord(
                    lesson_id=lesson.id, requested_starts_at=starts_at
                )
                session.add(request)
                session.flush()
                result = self._move_request_model(request)
            return result
        except IntegrityError as error:
            raise StoreError(
                409, "SLOT_TAKEN", "Someone just took that time. Here are the times still open."
            ) from error

    def approve_lesson_move(self, request_id: int) -> Lesson:
        try:
            with self._lock, self._sessions.begin() as session:
                request = session.get(LessonMoveRequestRecord, request_id)
                if request is None:
                    raise StoreError(404, "NOT_FOUND", "Move request not found.")
                lesson = session.get(LessonRecord, request.lesson_id)
                if lesson is None:
                    session.delete(request)
                    raise StoreError(404, "NOT_FOUND", "Lesson not found.")
                requested_date = self._studio(request.requested_starts_at).date()
                available = self._open_slots(
                    session,
                    requested_date,
                    requested_date,
                    lesson.id,
                    request.id,
                )
                if self._studio(request.requested_starts_at) not in available:
                    raise StoreError(
                        409,
                        "SLOT_TAKEN",
                        "That requested time is no longer available.",
                    )
                lesson.starts_at = request.requested_starts_at
                session.delete(request)
                session.flush()
                result = self._lesson_model(lesson)
            return result
        except IntegrityError as error:
            raise StoreError(409, "SLOT_TAKEN", "That requested time is no longer available.") from error

    # --- Pausing a student -------------------------------------------------
    #
    # A pause is a shift, not a flag. Setting `students.status` to `paused` and
    # stopping there is the bug #12 exists to fix: the lessons stayed on the
    # calendar, so the weekly slot everybody had been told was released was
    # still occupied.
    #
    # Pausing for `weeks` moves every one of the student's still-scheduled
    # lessons forward by exactly that many weeks, in the same transaction as
    # the status change. That one shift does both jobs: it leaves the paused
    # weeks empty -- so `_open_slots` offers those times to any other student
    # the moment the pause is written, with no separate "release" step to
    # forget -- and it pushes the rest of the package out by the same amount,
    # so the break costs the student nothing. `seq`, `used` and the number of
    # lessons never change.
    #
    # Resuming, early or when `ends_on` arrives, moves nothing back. Lessons
    # keep the dates the shift gave them even when the original slot is still
    # free; reclaiming it is #45, deliberately not decided here.

    PAUSE_WEEKS = range(1, 7)

    @classmethod
    def _pause_weeks(cls, value: object) -> int:
        """The requested break length, or one named error for everything else.

        The range lives here rather than on the request model so that 0, -2, 7
        and "three" all come back as `INVALID_PAUSE_LENGTH` instead of a
        generic validation failure -- the endpoints take `weeks` untyped and
        hand it straight over. `bool` is rejected explicitly because `True` is
        an `int` in Python, and `{"weeks": true}` is not a break length.
        """
        if isinstance(value, bool) or not isinstance(value, int) or value not in cls.PAUSE_WEEKS:
            raise StoreError(
                400, "INVALID_PAUSE_LENGTH", "A break is a whole number of weeks, from 1 to 6."
            )
        return value

    @staticmethod
    def _latest_pause_record(session: Session, student_id: int) -> StudentPauseRecord | None:
        return session.scalar(
            select(StudentPauseRecord)
            .where(StudentPauseRecord.student_id == student_id)
            .order_by(StudentPauseRecord.starts_on.desc(), StudentPauseRecord.id.desc())
            .limit(1)
        )

    @classmethod
    def _paused_until(cls, session: Session, record: StudentRecord) -> date | None:
        """The date a paused student is due back, when a pause row says so.

        None for anyone who is not paused, and also for a student whose status
        was set to `paused` without a pause row behind it -- the seeded studio
        has one, and a database written before this table existed can too.
        """
        if record.status != StudentStatus.PAUSED.value:
            return None
        pause = cls._latest_pause_record(session, record.id)
        if pause is None or pause.ended_early_at is not None:
            return None
        return pause.ends_on

    def _shift_lessons_forward(
        self, session: Session, student_id: int, from_date: date, weeks: int
    ) -> None:
        """Move the student's scheduled lessons from `from_date` on by `weeks`.

        Latest lesson first, one statement each. Every lesson lands on the slot
        the following one is about to vacate, so shifting in ascending order
        would collide with the student's own un-moved lessons on a `starts_at`
        that is unique across the whole studio; descending order never does.
        The updates are issued explicitly rather than by mutating the mapped
        objects because the order the unit of work would flush them in is not
        the order this needs.

        The shift is applied to the studio-local date and recombined with the
        same local time, not added to the instant, so a lesson keeps its
        wall-clock time across a daylight-saving change.
        """
        scheduled = session.scalars(
            select(LessonRecord).where(
                LessonRecord.student_id == student_id,
                LessonRecord.status == LessonStatus.SCHEDULED.value,
            )
        ).all()
        upcoming = [
            lesson for lesson in scheduled if self._studio(lesson.starts_at).date() >= from_date
        ]
        for lesson in sorted(upcoming, key=lambda record: record.starts_at, reverse=True):
            local = self._studio(lesson.starts_at)
            session.execute(
                update(LessonRecord)
                .where(LessonRecord.id == lesson.id)
                .values(
                    starts_at=self._at(
                        local.date() + timedelta(weeks=weeks), local.strftime("%H:%M")
                    )
                )
            )
        # The statements above went round the mapped objects, so what the
        # session still holds for those lessons is out of date.
        session.expire_all()

    def pause_student(self, student_id: int, weeks: object) -> Student:
        length = self._pause_weeks(weeks)
        # Settle the clock before shifting anything. A lesson whose time has
        # already passed is completed here rather than dragged forward, so a
        # pause never moves a lesson that already happened, and never leaves one
        # sitting in the past to be swept and charged to the package a moment
        # later by the very next read.
        self.catch_up()
        try:
            with self._lock, self._sessions.begin() as session:
                student = self._student_record(session, student_id)
                if student.status == StudentStatus.PAUSED.value:
                    raise StoreError(403, "STUDENT_PAUSED", "These lessons are already paused.")
                if student.status == StudentStatus.FLAGGED.value:
                    raise StoreError(
                        403,
                        "STUDENT_FLAGGED",
                        "There's an open question on this account. Sort that out first.",
                    )
                # A pause never silently cancels a move request: the student
                # would watch it vanish without an answer. The teacher approves
                # or declines it, then the break can be taken.
                pending = session.scalar(
                    select(LessonMoveRequestRecord.id)
                    .join(LessonRecord, LessonRecord.id == LessonMoveRequestRecord.lesson_id)
                    .where(LessonRecord.student_id == student.id)
                    .limit(1)
                )
                if pending is not None:
                    raise StoreError(
                        409,
                        "MOVE_REQUEST_PENDING",
                        "There's a move request waiting for an answer. Settle that first.",
                    )
                starts_on = clock.now().date()
                ends_on = starts_on + timedelta(weeks=length)
                self._shift_lessons_forward(session, student.id, starts_on, length)
                session.add(
                    StudentPauseRecord(
                        student_id=student.id,
                        weeks=length,
                        starts_on=starts_on,
                        ends_on=ends_on,
                        created_at=clock.now(),
                        ended_early_at=None,
                    )
                )
                student.status = StudentStatus.PAUSED.value
                session.flush()
                result = self._student_model(session, student)
            return result
        except IntegrityError as error:
            # A shifted lesson landed on a time another student already holds.
            # The transaction rolls back whole: no lesson is left half-moved and
            # no pause is recorded.
            raise StoreError(
                409, "SLOT_TAKEN", "A lesson would land on a time that is already taken."
            ) from error

    def resume_student(self, student_id: int) -> Student:
        """End a break now, leaving every lesson where the pause put it."""
        self.catch_up()
        with self._lock, self._sessions.begin() as session:
            student = self._student_record(session, student_id)
            if student.status != StudentStatus.PAUSED.value:
                raise StoreError(409, "STUDENT_NOT_PAUSED", "These lessons are not paused.")
            pause = self._latest_pause_record(session, student.id)
            if pause is not None and pause.ended_early_at is None:
                pause.ended_early_at = clock.now()
            student.status = StudentStatus.ACTIVE.value
            session.flush()
            return self._student_model(session, student)

    def expire_due_pauses(self) -> int:
        """Return every student whose break has run out to `active`, on read.

        The same catch-up-on-read pattern as `complete_due_lessons`, reading the
        same clock, for the same reason: nothing in this app notices time
        passing by itself, and a scheduled job is infrastructure it does not
        have (#43). A break covers `[starts_on, ends_on)`, so it is over once
        today has reached `ends_on`.

        No lesson moves here -- the shift already happened when the pause was
        requested. `ended_early_at` is left null, and that is what tells a
        break that simply ran out apart from one `resume_student` ended.
        """
        today = clock.now().date()
        with self._lock, self._sessions.begin() as session:
            paused = session.scalars(
                select(StudentRecord).where(StudentRecord.status == StudentStatus.PAUSED.value)
            ).all()
            resumed = 0
            for student in paused:
                pause = self._latest_pause_record(session, student.id)
                # Only the most recent pause decides. An older, expired row must
                # never end a break that was requested after it.
                if pause is None or pause.ended_early_at is not None or pause.ends_on > today:
                    continue
                student.status = StudentStatus.ACTIVE.value
                resumed += 1
            return resumed

    def catch_up(self) -> None:
        """Everything the clock has quietly made true since the last read.

        The read endpoints call this single method so the two catch-ups cannot
        drift apart: lessons whose time has passed are completed, and breaks
        that have run out are lifted.
        """
        self.complete_due_lessons()
        self.expire_due_pauses()

    def set_hours(self, day: int, times: list[str]) -> None:
        with self._sessions.begin() as session:
            session.execute(
                delete(AvailabilitySlotRecord).where(AvailabilitySlotRecord.weekday == day)
            )
            session.add_all(
                AvailabilitySlotRecord(weekday=day, local_time=slot_time) for slot_time in times
            )

    def add_blackout(self, starts_at: datetime, note: str) -> Blackout:
        with self._sessions.begin() as session:
            record = BlackoutRecord(starts_at=starts_at, note=note.strip())
            session.add(record)
            session.flush()
            return self._blackout_model(record)

    def remove_blackout(self, blackout_id: int) -> None:
        with self._sessions.begin() as session:
            record = session.get(BlackoutRecord, blackout_id)
            if record is None:
                raise StoreError(404, "NOT_FOUND", "Blackout not found.")
            session.delete(record)

    def create_student(self, name: str, slot_day: int, slot_time: str) -> Student:
        with self._sessions.begin() as session:
            student = StudentRecord(
                name=name.strip(),
                status=StudentStatus.ACTIVE.value,
                token=secrets.token_urlsafe(24),
                slot_day=slot_day,
                slot_time=slot_time,
            )
            session.add(student)
            session.flush()
            session.add(
                PackageRecord(
                    student_id=student.id,
                    size=10,
                    used=0,
                    period_no=1,
                    invoice_sent=False,
                )
            )
            session.flush()
            return self._student_model(session, student)

    def set_student_slot(self, student_id: int, slot_day: int, slot_time: str) -> None:
        with self._sessions.begin() as session:
            student = self._student_record(session, student_id)
            student.slot_day = slot_day
            student.slot_time = slot_time

    def set_student_status(self, student_id: int, status: StudentStatus) -> None:
        # Exactly one path into a pause. This endpoint only ever flipped the
        # column, which is precisely the bug #12 fixes, so the bug cannot come
        # back through it: `pause_student` is the only thing that both flips the
        # status and frees the slot.
        if status == StudentStatus.PAUSED:
            raise StoreError(
                400,
                "USE_PAUSE_ENDPOINT",
                "Pause a student with POST /admin/students/{id}/pause, which frees their slot.",
            )
        with self._sessions.begin() as session:
            self._student_record(session, student_id).status = status.value

    @staticmethod
    def _next_weekly_slot_date(on_or_after: date, slot_day: int) -> date:
        """The first `slot_day` falling on or after `on_or_after`."""
        return on_or_after + timedelta(days=(slot_day - 1 - on_or_after.weekday()) % 7)

    def _fresh_package_anchor(self, student: StudentRecord) -> date:
        """Where a package with no history behind it starts: next week's slot."""
        monday = self._monday(datetime.now(STUDIO_TZ).date()) + timedelta(weeks=1)
        return monday + timedelta(days=student.slot_day - 1)

    def _place_weekly_lessons(
        self,
        session: Session,
        student: StudentRecord,
        package_id: int,
        *,
        count: int,
        first_seq: int,
        first_date: date,
    ) -> None:
        """`count` lessons, one per week, from `first_date` on the weekly slot.

        The only place lesson dates are generated, used both by opening a
        package and by renewing one, so the two cannot drift apart. It is
        blackout- and availability-blind on purpose: a generated date can land
        on a blackout or outside the grid, exactly as it does today. Fixing that
        is #11, and fixing it here fixes it for both callers at once.
        """
        for index in range(count):
            self._add_lesson_record(
                session,
                student.id,
                package_id,
                first_seq + index,
                self._at(first_date + timedelta(weeks=index), student.slot_time),
            )

    def _open_package_record(
        self,
        session: Session,
        student: StudentRecord,
        size: int,
    ) -> None:
        scheduled = session.scalar(
            select(func.count())
            .select_from(LessonRecord)
            .where(
                LessonRecord.student_id == student.id,
                LessonRecord.status == LessonStatus.SCHEDULED.value,
            )
        )
        if scheduled:
            raise StoreError(409, "PACKAGE_OPEN", "This student already has scheduled lessons.")
        current_package = self._current_package(session, student.id)
        package = PackageRecord(
            student_id=student.id,
            size=size,
            used=0,
            period_no=current_package.period_no + 1,
            invoice_sent=False,
        )
        session.add(package)
        session.flush()
        self._place_weekly_lessons(
            session,
            student,
            package.id,
            count=size,
            first_seq=1,
            first_date=self._fresh_package_anchor(student),
        )

    def open_package(self, student_id: int, size: int) -> None:
        try:
            with self._sessions.begin() as session:
                self._open_package_record(session, self._student_record(session, student_id), size)
        except IntegrityError as error:
            raise StoreError(
                409, "SLOT_TAKEN", "A generated lesson time is already booked."
            ) from error

    def renew_package(self, student_id: int, size: int) -> None:
        """Top the student's current package up by `size` lessons (#13).

        A renewal extends what is already there rather than starting something
        new: `size` goes up on the existing row, `period_no` and `used` are left
        alone, no already-scheduled lesson is touched, and `size` more lessons
        are appended to the end of the schedule. So a 10-lesson package with 7
        done, renewed by 10, reads 7/20 with the run of lessons continuing
        unbroken -- which is the thing the old "open a new package" path could
        not do while lessons were still scheduled.

        What that costs: the row keeps no record of what was sold when. A 20 is
        a 20, whether it was 10 + 10 or 8 + 8 + 4. That was decided on #13 and
        an audit table can be added later without changing this.

        Statuses do not block it. Renewing is the teacher acting on a student's
        behalf; flagging only stops the *student's* own booking and moves, and a
        paused student can be sold lessons for after the break -- which is why
        the anchor below takes the pause into account.
        """
        try:
            with self._lock, self._sessions.begin() as session:
                student = self._student_record(session, student_id)
                package = self._current_package(session, student.id)
                last = session.scalar(
                    select(LessonRecord)
                    .where(LessonRecord.package_id == package.id)
                    .order_by(LessonRecord.starts_at.desc())
                    .limit(1)
                )
                highest_seq = (
                    session.scalar(
                        select(func.max(LessonRecord.seq)).where(
                            LessonRecord.package_id == package.id
                        )
                    )
                    or 0
                )
                # The day after the package's last lesson, done or scheduled --
                # a renewal continues the schedule rather than restarting it. A
                # package that never got any lessons (opened at student creation
                # and never populated) starts where a fresh one would.
                if last is None:
                    earliest = self._fresh_package_anchor(student)
                else:
                    earliest = self._studio(last.starts_at).date() + timedelta(days=1)
                # Never inside a break. #12's forward shift already pushed the
                # scheduled lessons past `ends_on`, so this only bites when the
                # package has no lessons left to follow -- but it is the real
                # pause date either way, not an approximation of one.
                paused_until = self._paused_until(session, student)
                if paused_until is not None and paused_until > earliest:
                    earliest = paused_until
                package.size += size
                # The package is no longer finished, so whatever invoice was
                # sent for it does not cover it. It goes back on the list.
                package.invoice_sent = False
                self._place_weekly_lessons(
                    session,
                    student,
                    package.id,
                    count=size,
                    first_seq=highest_seq + 1,
                    first_date=self._next_weekly_slot_date(earliest, student.slot_day),
                )
        except IntegrityError as error:
            raise StoreError(
                409, "SLOT_TAKEN", "A generated lesson time is already booked."
            ) from error

    def mark_invoiced(self, package_id: int) -> None:
        """Record that the invoice for this package went out. Nothing else.

        It used to open the next package as a side effect, which meant the
        teacher never got to say how big that package should be -- it silently
        reused the size of the one just finished -- and marking an invoice sent
        quietly filled the calendar. Selling more lessons is now its own
        deliberate action: `renew_package` to top this package up, or
        `open_package` for a genuinely fresh one (#13).
        """
        with self._sessions.begin() as session:
            package = session.get(PackageRecord, package_id)
            if package is None:
                raise StoreError(404, "NOT_FOUND", "Package not found.")
            if package.used < package.size:
                raise StoreError(
                    400, "PACKAGE_NOT_CONSUMED", "This package is not ready to invoice."
                )
            package.invoice_sent = True

    def remove_lesson(self, lesson_id: int) -> None:
        with self._sessions.begin() as session:
            lesson = session.get(LessonRecord, lesson_id)
            if lesson is None:
                raise StoreError(404, "NOT_FOUND", "Lesson not found.")
            session.execute(
                delete(LessonMoveRequestRecord).where(
                    LessonMoveRequestRecord.lesson_id == lesson_id
                )
            )
            session.delete(lesson)

    # --- Lesson completion -------------------------------------------------
    #
    # Design decision: catch-up-on-read, not a scheduled job.
    #
    # A lesson that has started is completed by the next request that reads the
    # data it affects (`GET /admin/students`, `GET /admin/students/{id}`,
    # `GET /admin/api/week`, `GET /admin/alerts`, `GET /s/{token}`), which is
    # why `complete_due_lessons` is called from those handlers.
    #
    # The trade-off, stated plainly: a package that finished days ago keeps
    # reading as unconsumed, and its invoice alert stays silent, until somebody
    # reads that studio's data. Nothing here notices time passing on its own.
    # The alternative -- a nightly job -- is a process that has to be deployed,
    # run and monitored, which is new infrastructure this app has none of today
    # (`_docs/specs.md` section 6's nightly job was never built). A real
    # scheduled job is filed separately as #43 for when that gap starts to
    # matter in practice.
    #
    # "Past" is measured against `clock.now()` in `STUDIO_TZ`, the same clock
    # `is_day_locked` uses. Sweeping is global rather than per student: it is a
    # single indexed query, and it keeps every read seeing the same world.

    def _due_lesson_records(self, session: Session, now: datetime) -> list[LessonRecord]:
        """Every lesson that has started and is still marked scheduled.

        Only `status` and `starts_at` decide this. A paused or flagged student's
        lesson is swept exactly like an active student's (whether pausing should
        have released the lesson at all is #12's job), and a lesson deleted via
        `DELETE /admin/lessons/{id}` is not a row any more, so it is never seen
        here -- there is no `cancelled` status to exempt today (see #44).
        """
        return list(
            session.scalars(
                select(LessonRecord)
                .where(
                    LessonRecord.status == LessonStatus.SCHEDULED.value,
                    LessonRecord.starts_at <= now,
                )
                .order_by(LessonRecord.starts_at, LessonRecord.id)
            )
        )

    @staticmethod
    def _consume_package_credit(session: Session, lesson: LessonRecord) -> bool:
        """Count one lesson against its package, never past `size`.

        `packages.used <= size` is a database CHECK constraint, so going past it
        is a crash, not a wrong number. A package that is already full keeps its
        count and the lesson is still completed by the caller, so it stops
        showing up as an overdue "scheduled" lesson on the calendar.
        """
        package = session.get(PackageRecord, lesson.package_id)
        if package is None:
            raise RuntimeError(f"Lesson {lesson.id} points at a package that does not exist")
        if package.used >= package.size:
            return False
        package.used += 1
        return True

    def complete_due_lessons(self) -> int:
        """Mark every started lesson done, once, and return how many were swept.

        Idempotent: the transition is what guards it. A second sweep no longer
        matches a lesson it has already completed, so `used` goes up by exactly
        one per lesson however many times this runs. The single-writer lock is
        held across the read and the write, so two overlapping requests are
        serialised rather than both seeing the same lesson as scheduled.
        """
        now = clock.now()
        with self._lock, self._sessions.begin() as session:
            due = self._due_lesson_records(session, now)
            for lesson in due:
                lesson.status = LessonStatus.DONE.value
                self._consume_package_credit(session, lesson)
            return len(due)

    def complete_lesson(self, lesson_id: int) -> Lesson:
        """Mark one lesson done by hand, including one that has not started yet.

        The admin override for "the lesson happened" -- an early completion, or
        a lesson the sweep has not reached because nothing has read this studio's
        data since it started.
        """
        with self._lock, self._sessions.begin() as session:
            lesson = session.get(LessonRecord, lesson_id)
            if lesson is None:
                raise StoreError(404, "NOT_FOUND", "Lesson not found.")
            if lesson.status == LessonStatus.DONE.value:
                raise StoreError(
                    409, "LESSON_ALREADY_DONE", "That lesson is already marked done."
                )
            # Unlike the sweep, an explicit admin action on a full package fails
            # loudly instead of completing the lesson without counting it: the
            # sweep has no one to tell, this endpoint does.
            if not self._consume_package_credit(session, lesson):
                raise StoreError(
                    409,
                    "PACKAGE_FULL",
                    "This package has no lessons left to use. Undo another lesson first.",
                )
            lesson.status = LessonStatus.DONE.value
            session.flush()
            return self._lesson_model(lesson)

    def uncomplete_lesson(self, lesson_id: int) -> Lesson:
        """Undo a completion: back to scheduled, one lesson back on the package.

        Undoing a lesson whose time has already passed puts it straight back
        into the set the sweep matches, so the next read marks it done again.
        That is expected, not a bug: completion is derived from the clock, and
        the way to keep a past lesson from coming back is to delete it. A
        first-class `cancelled` status that would not need the two-step is #44.
        """
        with self._lock, self._sessions.begin() as session:
            lesson = session.get(LessonRecord, lesson_id)
            if lesson is None:
                raise StoreError(404, "NOT_FOUND", "Lesson not found.")
            if lesson.status != LessonStatus.DONE.value:
                raise StoreError(409, "LESSON_NOT_DONE", "That lesson is not marked done.")
            package = session.get(PackageRecord, lesson.package_id)
            if package is None:
                raise RuntimeError(f"Lesson {lesson.id} points at a package that does not exist")
            if package.used <= 0:
                raise StoreError(
                    409, "PACKAGE_EMPTY", "This package has no used lessons to give back."
                )
            package.used -= 1
            lesson.status = LessonStatus.SCHEDULED.value
            session.flush()
            return self._lesson_model(lesson)

    def list_move_requests(
        self,
    ) -> list[tuple[Student, Lesson, LessonMoveRequest]]:
        with self._sessions() as session:
            requests = session.scalars(
                select(LessonMoveRequestRecord).order_by(
                    LessonMoveRequestRecord.requested_starts_at,
                    LessonMoveRequestRecord.id,
                )
            ).all()
            result = []
            for request in requests:
                lesson = session.get(LessonRecord, request.lesson_id)
                if lesson is None:
                    continue
                student_record = self._student_record(session, lesson.student_id)
                result.append(
                    (
                        self._student_model(session, student_record),
                        self._lesson_model(lesson),
                        self._move_request_model(request),
                    )
                )
            return result

    def list_alerts(self) -> list[tuple[Student, Package]]:
        with self._sessions() as session:
            packages = session.scalars(
                select(PackageRecord).where(
                    PackageRecord.used >= PackageRecord.size,
                    PackageRecord.invoice_sent.is_(False),
                )
            ).all()
            result = []
            for package in packages:
                student_record = self._student_record(session, package.student_id)
                student = self._student_model(session, student_record)
                result.append(
                    (
                        student,
                        Package(
                            id=package.id,
                            size=package.size,
                            used=package.used,
                            periodNo=package.period_no,
                        ),
                    )
                )
            return result


store = DatabaseStore()
