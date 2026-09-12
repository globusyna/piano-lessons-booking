from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from threading import RLock
from zoneinfo import ZoneInfo

from .auth import hash_password
from .models import Lesson, LessonStatus, Package, Student, StudentStatus


STUDIO_TZ = ZoneInfo("Europe/Oslo")
ROW_TIMES = ["14:00", "14:45", "15:30", "16:15", "17:00", "17:45", "18:30"]


@dataclass
class BlackoutRecord:
    id: int
    starts_at: datetime
    note: str


class StoreError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class MemoryStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.admin_username = "admin"
            self.admin_password_hash = hash_password("piano")
            self.students: dict[int, Student] = {}
            self.lessons: dict[int, Lesson] = {}
            self.blackouts: dict[int, BlackoutRecord] = {}
            self.hours: dict[int, list[str]] = {
                1: ROW_TIMES[1:],
                2: ROW_TIMES[:],
                3: ROW_TIMES[:-1],
                4: ROW_TIMES[:],
                5: ROW_TIMES[:-2],
            }
            self._next_student = 1
            self._next_lesson = 401
            self._next_package = 1
            self._next_blackout = 1
            seeds = [
                ("Anna Lie", "anna", StudentStatus.ACTIVE, 2, "16:15", 10, 7, 3, False),
                ("Jonas Berg", "jonas", StudentStatus.ACTIVE, 1, "15:30", 10, 10, 2, False),
                ("Mira Solheim", "mira", StudentStatus.PAUSED, 3, "17:00", 8, 4, 1, False),
                ("Teodor Haugen", "teodor", StudentStatus.FLAGGED, 4, "14:45", 10, 3, 5, False),
                ("Selma Ruud", "selma", StudentStatus.ACTIVE, 5, "17:45", 10, 2, 1, False),
                ("Oskar Dahl", "oskar", StudentStatus.ACTIVE, 2, "18:30", 10, 9, 4, False),
            ]
            monday = self._monday(datetime.now(STUDIO_TZ).date())
            for name, token, status, day, slot_time, size, used, period, invoiced in seeds:
                package = Package(id=self._take_package_id(), size=size, used=used, periodNo=period)
                student = Student(
                    id=self._next_student,
                    name=name,
                    status=status,
                    token=token,
                    slotDay=day,
                    slotTime=slot_time,
                    pkg=package,
                    invoiceSent=invoiced,
                )
                self.students[student.id] = student
                self._next_student += 1
                for seq in range(1, used + 1):
                    lesson_day = monday + timedelta(days=day - 1, weeks=seq - used - 1)
                    self._add_lesson(student.id, seq, self._at(lesson_day, slot_time), LessonStatus.DONE)
                for seq in range(used + 1, size + 1):
                    lesson_day = monday + timedelta(days=day - 1, weeks=seq - used)
                    self._add_lesson(student.id, seq, self._at(lesson_day, slot_time))
            self.add_blackout(self._at(monday + timedelta(days=2), "17:00"), "Dentist")
            self.add_blackout(self._at(monday + timedelta(days=9), "14:00"), "Recital rehearsal")

    @staticmethod
    def _monday(value: date) -> date:
        return value - timedelta(days=value.weekday())

    @staticmethod
    def _at(value: date, local_time: str) -> datetime:
        hour, minute = map(int, local_time.split(":"))
        return datetime.combine(value, time(hour, minute), STUDIO_TZ)

    def _take_package_id(self) -> int:
        value = self._next_package
        self._next_package += 1
        return value

    def _add_lesson(
        self, student_id: int, seq: int, starts_at: datetime, status: LessonStatus = LessonStatus.SCHEDULED
    ) -> Lesson:
        lesson = Lesson(
            id=self._next_lesson,
            seq=seq,
            studentId=student_id,
            startsAt=starts_at,
            status=status,
        )
        self.lessons[lesson.id] = lesson
        self._next_lesson += 1
        return lesson

    def student_for_token(self, token: str) -> Student:
        student = next((item for item in self.students.values() if item.token == token), None)
        if student is None:
            raise StoreError(404, "INVALID_TOKEN", "This link isn't valid. Ask your teacher for a new one.")
        return student

    def student(self, student_id: int) -> Student:
        student = self.students.get(student_id)
        if student is None:
            raise StoreError(404, "NOT_FOUND", "Student not found.")
        return student

    def lesson_history(self, student_id: int) -> list[Lesson]:
        return sorted(
            (lesson for lesson in self.lessons.values() if lesson.student_id == student_id),
            key=lambda lesson: lesson.starts_at,
        )

    def is_day_locked(self, starts_at: datetime) -> bool:
        return starts_at.astimezone(STUDIO_TZ).date() < datetime.now(STUDIO_TZ).date()

    def in_move_window(self, starts_at: datetime) -> bool:
        local = starts_at.astimezone(STUDIO_TZ)
        today = datetime.now(STUDIO_TZ).date()
        return local > datetime.now(STUDIO_TZ) and today <= local.date() <= today + timedelta(days=21)

    def open_slots(self, from_date: date, to_date: date, exclude_lesson_id: int | None = None) -> list[datetime]:
        if from_date > to_date:
            raise StoreError(400, "INVALID_RANGE", "The start date must be on or before the end date.")
        today = datetime.now(STUDIO_TZ).date()
        first, last = max(from_date, today), min(to_date, today + timedelta(days=21))
        if first > last:
            return []
        taken = {
            lesson.starts_at
            for lesson in self.lessons.values()
            if lesson.status == LessonStatus.SCHEDULED and lesson.id != exclude_lesson_id
        }
        blocked = {blackout.starts_at for blackout in self.blackouts.values()}
        slots: list[datetime] = []
        current = first
        while current <= last:
            day = current.isoweekday()
            for slot_time in self.hours.get(day, []):
                candidate = self._at(current, slot_time)
                if candidate not in taken and candidate not in blocked and self.in_move_window(candidate):
                    slots.append(candidate)
            current += timedelta(days=1)
        return sorted(slots)

    def move_lesson(self, token: str, lesson_id: int, starts_at: datetime) -> Lesson:
        with self._lock:
            student = self.student_for_token(token)
            lesson = self.lessons.get(lesson_id)
            if lesson is None or lesson.student_id != student.id:
                raise StoreError(404, "INVALID_TOKEN", "This link isn't valid. Ask your teacher for a new one.")
            if student.status == StudentStatus.PAUSED:
                raise StoreError(403, "STUDENT_PAUSED", "Your lessons are paused. Your teacher will be in touch.")
            if student.status == StudentStatus.FLAGGED:
                raise StoreError(403, "STUDENT_FLAGGED", "There's an open question on your account. Your teacher will be in touch.")
            if self.is_day_locked(lesson.starts_at):
                raise StoreError(403, "DAY_LOCKED", "That day is closed for changes.")
            if not self.in_move_window(starts_at):
                raise StoreError(400, "OUTSIDE_WINDOW", "That time is outside the booking window.")
            available = self.open_slots(starts_at.astimezone(STUDIO_TZ).date(), starts_at.astimezone(STUDIO_TZ).date(), lesson.id)
            if starts_at not in available:
                raise StoreError(409, "SLOT_TAKEN", "Someone just took that time. Here are the times still open.")
            lesson.starts_at = starts_at.astimezone(STUDIO_TZ)
            return lesson

    def pause(self, token: str) -> Student:
        student = self.student_for_token(token)
        if student.status != StudentStatus.ACTIVE:
            code = "STUDENT_PAUSED" if student.status == StudentStatus.PAUSED else "STUDENT_FLAGGED"
            raise StoreError(403, code, "A break cannot be requested in the current account state.")
        student.status = StudentStatus.PAUSED
        return student

    def add_blackout(self, starts_at: datetime, note: str) -> BlackoutRecord:
        blackout = BlackoutRecord(self._next_blackout, starts_at.astimezone(STUDIO_TZ), note.strip())
        self.blackouts[blackout.id] = blackout
        self._next_blackout += 1
        return blackout

    def remove_blackout(self, blackout_id: int) -> None:
        if self.blackouts.pop(blackout_id, None) is None:
            raise StoreError(404, "NOT_FOUND", "Blackout not found.")

    def create_student(self, name: str, slot_day: int, slot_time: str) -> Student:
        package = Package(id=self._take_package_id(), size=10, used=0, periodNo=1)
        student = Student(
            id=self._next_student,
            name=name.strip(),
            status=StudentStatus.ACTIVE,
            token=secrets.token_urlsafe(24),
            slotDay=slot_day,
            slotTime=slot_time,
            pkg=package,
            invoiceSent=False,
        )
        self.students[student.id] = student
        self._next_student += 1
        return student

    def open_package(self, student_id: int, size: int, *, replacing_invoiced: bool = False) -> None:
        student = self.student(student_id)
        scheduled = [lesson for lesson in self.lesson_history(student_id) if lesson.status == LessonStatus.SCHEDULED]
        if scheduled and not replacing_invoiced:
            raise StoreError(409, "PACKAGE_OPEN", "This student already has scheduled lessons.")
        package = Package(
            id=self._take_package_id(), size=size, used=0, periodNo=student.pkg.period_no + 1
        )
        student.pkg = package
        student.invoice_sent = False
        monday = self._monday(datetime.now(STUDIO_TZ).date()) + timedelta(weeks=1)
        for index in range(size):
            lesson_date = monday + timedelta(days=student.slot_day - 1, weeks=index)
            self._add_lesson(student.id, index + 1, self._at(lesson_date, student.slot_time))

    def mark_invoiced(self, package_id: int) -> None:
        student = next((item for item in self.students.values() if item.pkg.id == package_id), None)
        if student is None:
            raise StoreError(404, "NOT_FOUND", "Package not found.")
        if student.pkg.used < student.pkg.size:
            raise StoreError(400, "PACKAGE_NOT_CONSUMED", "This package is not ready to invoice.")
        size = student.pkg.size
        student.invoice_sent = True
        self.open_package(student.id, size, replacing_invoiced=True)


store = MemoryStore()
