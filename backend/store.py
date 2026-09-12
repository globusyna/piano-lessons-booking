from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from threading import RLock
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import hash_password
from .database import create_database_engine, create_session_factory
from .db_models import (
    AvailabilitySlotRecord,
    BlackoutRecord,
    LessonMoveRequestRecord,
    LessonRecord,
    PackageRecord,
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
    """The one "now" the lesson completion logic reads.

    Completion is the only behaviour in the store that has to be driven from a
    test at an exact instant -- the moment a package's last lesson passes -- and
    a test cannot wait for that instant to arrive. So the completion code path
    asks this object for the time instead of calling ``datetime.now`` inline,
    and a test pins it:

        with clock.pinned(last_lesson_starts_at):
            client.get("/admin/alerts", headers=admin_headers)

    Deliberately narrow: only the completion path reads it today. Giving the
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
            downgrade_to_base(self.engine)
            upgrade_to_head(self.engine)
            self._seed_if_empty()

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

    def pause(self, token: str) -> Student:
        with self._sessions.begin() as session:
            student = self._student_for_token_record(session, token)
            if student.status != StudentStatus.ACTIVE.value:
                code = (
                    "STUDENT_PAUSED"
                    if student.status == StudentStatus.PAUSED.value
                    else "STUDENT_FLAGGED"
                )
                raise StoreError(
                    403, code, "A break cannot be requested in the current account state."
                )
            student.status = StudentStatus.PAUSED.value
            session.flush()
            return self._student_model(session, student)

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
        with self._sessions.begin() as session:
            self._student_record(session, student_id).status = status.value

    def _open_package_record(
        self,
        session: Session,
        student: StudentRecord,
        size: int,
        replacing_invoiced: bool = False,
    ) -> None:
        scheduled = session.scalar(
            select(func.count())
            .select_from(LessonRecord)
            .where(
                LessonRecord.student_id == student.id,
                LessonRecord.status == LessonStatus.SCHEDULED.value,
            )
        )
        if scheduled and not replacing_invoiced:
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
        monday = self._monday(datetime.now(STUDIO_TZ).date()) + timedelta(weeks=1)
        for index in range(size):
            lesson_date = monday + timedelta(days=student.slot_day - 1, weeks=index)
            self._add_lesson_record(
                session,
                student.id,
                package.id,
                index + 1,
                self._at(lesson_date, student.slot_time),
            )

    def open_package(self, student_id: int, size: int) -> None:
        try:
            with self._sessions.begin() as session:
                self._open_package_record(session, self._student_record(session, student_id), size)
        except IntegrityError as error:
            raise StoreError(
                409, "SLOT_TAKEN", "A generated lesson time is already booked."
            ) from error

    def mark_invoiced(self, package_id: int) -> None:
        try:
            with self._sessions.begin() as session:
                package = session.get(PackageRecord, package_id)
                if package is None:
                    raise StoreError(404, "NOT_FOUND", "Package not found.")
                if package.used < package.size:
                    raise StoreError(
                        400, "PACKAGE_NOT_CONSUMED", "This package is not ready to invoice."
                    )
                package.invoice_sent = True
                student = self._student_record(session, package.student_id)
                self._open_package_record(session, student, package.size, replacing_invoiced=True)
        except IntegrityError as error:
            raise StoreError(
                409, "SLOT_TAKEN", "A generated lesson time is already booked."
            ) from error

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
