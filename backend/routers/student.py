from datetime import date, datetime

from fastapi import APIRouter, Query

from ..models import RescheduleRequest, StudentLesson, StudentSummary, StudentView
from ..store import STUDIO_TZ, StoreError, store


router = APIRouter(prefix="/s", tags=["Student"])


def _view(token: str) -> StudentView:
    student = store.student_for_token(token)
    now = datetime.now(STUDIO_TZ)
    upcoming = [
        lesson
        for lesson in store.lesson_history(student.id)
        if lesson.status.value == "scheduled" and lesson.starts_at > now
    ]
    lessons = [
        StudentLesson(
            id=lesson.id,
            seq=lesson.seq,
            startsAt=lesson.starts_at,
            status=lesson.status,
            canMove=student.status.value == "active" and not store.is_day_locked(lesson.starts_at),
        )
        for lesson in upcoming
    ]
    return StudentView(
        student=StudentSummary(id=student.id, name=student.name, status=student.status),
        package=student.pkg,
        nextLesson=lessons[0] if lessons else None,
        lessons=lessons,
        canRequestPause=student.status.value == "active" and bool(lessons),
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
    lesson = store.move_lesson(token, lesson_id, body.starts_at)
    return {"ok": True, "data": lesson}


@router.post("/{token}/pause-request")
def request_pause(token: str) -> dict:
    student = store.pause(token)
    return {"ok": True, "data": student}
