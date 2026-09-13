from datetime import date, datetime

from fastapi import APIRouter, Query

from ..models import (
    Lesson,
    PauseRequest,
    RescheduleRequest,
    Student,
    StudentLesson,
    StudentSummary,
    StudentView,
)
from ..store import STUDIO_TZ, StoreError, store


router = APIRouter(prefix="/s", tags=["Student"])


def _student_lesson(lesson: Lesson, student: Student) -> StudentLesson:
    """One upcoming lesson, including what became of any request to move it.

    The move request is read once and its **status** is what everything here
    turns on. `is not None` used to be enough to mean "already asked, cannot ask
    again"; now that a declined or expired request survives, that test would
    leave the student staring at a Move button that never comes back. Only a
    pending request blocks, and only a pending one has a live requested time.
    """
    request = store.move_request_for_lesson(lesson.id)
    pending = request is not None and request.status == "pending"
    resolved = request if request is not None and not pending else None
    return StudentLesson(
        id=lesson.id,
        seq=lesson.seq,
        startsAt=lesson.starts_at,
        status=lesson.status,
        canMove=(
            student.status.value == "active"
            and store.can_request_lesson_move(lesson.starts_at)
            and not pending
        ),
        requestedStartsAt=request.requested_starts_at if pending else None,
        moveRequestStatus=resolved.status if resolved else None,
        declineReason=resolved.decline_reason if resolved else None,
    )


def _view(token: str) -> StudentView:
    # Catch-up-on-read: the student's own page is one of the reads that closes
    # out lessons whose time has passed and lifts a break that has run out
    # (see DatabaseStore.catch_up).
    store.catch_up()
    student = store.student_for_token(token)
    now = datetime.now(STUDIO_TZ)
    upcoming = [
        lesson
        for lesson in store.lesson_history(student.id)
        if lesson.status.value == "scheduled" and lesson.starts_at > now
    ]
    lessons = [_student_lesson(lesson, student) for lesson in upcoming]
    return StudentView(
        student=StudentSummary(id=student.id, name=student.name, status=student.status),
        package=student.pkg,
        nextLesson=lessons[0] if lessons else None,
        lessons=lessons,
        canRequestPause=student.status.value == "active" and bool(lessons),
        pausedUntil=student.paused_until,
    )


@router.get("/{token}", response_model=StudentView)
def get_student_view(token: str) -> StudentView:
    return _view(token)


@router.get("/{token}/slots")
def get_open_slots(
    token: str,
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
    lesson_id: int | None = Query(default=None, alias="lessonId", ge=1),
) -> dict:
    student = store.student_for_token(token)
    if lesson_id is not None:
        lesson = store.lesson(lesson_id)
        if lesson is None or lesson.student_id != student.id:
            raise StoreError(404, "INVALID_TOKEN", "This link isn't valid. Ask your teacher for a new one.")
    return {"slots": [{"startsAt": value} for value in store.open_slots(from_date, to_date, lesson_id)]}


@router.post("/{token}/lessons/{lesson_id}/reschedule")
def reschedule_lesson(token: str, lesson_id: int, body: RescheduleRequest) -> dict:
    request = store.request_lesson_move(token, lesson_id, body.starts_at)
    return {"ok": True, "data": request}


@router.post("/{token}/pause-request")
def request_pause(token: str, body: PauseRequest) -> dict:
    student = store.student_for_token(token)
    return {"ok": True, "data": store.pause_student(student.id, body.weeks)}
