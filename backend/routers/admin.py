from datetime import date, timedelta

from fastapi import APIRouter, Depends

from ..auth import require_admin
from ..models import (
    AvailabilityRequest,
    BlackoutRequest,
    DeclineMoveRequestBody,
    PackageRequest,
    PauseRequest,
    PurchasableSize,
    StatusRequest,
    StudentCreate,
    StudentSlotRequest,
)
from ..store import ROW_TIMES, StoreError, store


router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("/api/week")
def get_week(start: date) -> dict:
    store.catch_up()
    if start.weekday() != 0:
        raise StoreError(400, "INVALID_WEEK", "The requested week must start on Monday.")
    days = []
    for offset in range(5):
        day_date = start + timedelta(days=offset)
        cells = []
        for local_time in ROW_TIMES:
            starts_at = store._at(day_date, local_time)
            lesson = store.scheduled_lesson_at(starts_at)
            blackout = store.blackout_at(starts_at)
            if lesson:
                student = store.student(lesson.student_id)
                move_request = store.move_request_for_lesson(lesson.id)
                cells.append(
                    {
                        "type": "lesson",
                        "startsAt": starts_at,
                        "lessonId": lesson.id,
                        "studentName": student.name,
                        "seq": lesson.seq,
                        "size": student.pkg.size,
                        "moveRequest": move_request,
                    }
                )
            elif blackout:
                cells.append({"type": "blackout", "startsAt": starts_at, "note": blackout.note})
            else:
                cells.append({"type": "open", "startsAt": starts_at})
        days.append({"date": day_date, "locked": store.is_day_locked(store._at(day_date, "23:59")), "cells": cells})
    return {"days": days}


@router.get("/availability")
def get_availability() -> dict:
    return {
        "hours": store.hours,
        "blackouts": store.list_blackouts(),
    }


@router.post("/availability")
def set_availability(body: AvailabilityRequest) -> dict:
    store.set_hours(body.day, body.times)
    return {"ok": True}


@router.post("/blackout")
def add_blackout(body: BlackoutRequest) -> dict:
    blackout = store.add_blackout(body.starts_at, body.note)
    return {
        "ok": True,
        "data": {"id": blackout.id, "startsAt": blackout.starts_at, "note": blackout.note},
    }


@router.delete("/blackout/{blackout_id}")
def remove_blackout(blackout_id: int) -> dict:
    store.remove_blackout(blackout_id)
    return {"ok": True}


@router.get("/students")
def list_students() -> dict:
    store.catch_up()
    return {"students": store.list_students()}


@router.post("/students", status_code=201)
def create_student(body: StudentCreate) -> dict:
    return {
        "ok": True,
        "data": store.create_student(body.name, body.slot_day, body.slot_time),
    }


@router.get("/students/{student_id}")
def get_student(student_id: int) -> dict:
    store.catch_up()
    return {"student": store.student(student_id), "lessons": store.lesson_history(student_id)}


@router.post("/students/{student_id}/slot")
def set_student_slot(student_id: int, body: StudentSlotRequest) -> dict:
    store.set_student_slot(student_id, body.slot_day, body.slot_time)
    return {"ok": True}


@router.post("/students/{student_id}/package")
def open_student_package(student_id: int, body: PackageRequest) -> dict:
    store.open_package(student_id, body.size)
    return {"ok": True}


@router.post("/students/{student_id}/package/renew")
def renew_student_package(student_id: int, body: PackageRequest) -> dict:
    """Top the student's current package up, rather than opening a new one.

    Same body as opening a package, on purpose: what can be sold in one go is
    still 5, 8 or 10 lessons, whatever total the package has reached.
    """
    store.renew_package(student_id, body.size)
    return {"ok": True}


@router.get("/students/{student_id}/package/preview")
def preview_student_package(student_id: int, size: PurchasableSize) -> dict:
    """The dates opening a package would put on the calendar, creating nothing.

    A GET, because it changes nothing: the store runs the real generation path
    and stops short of writing (#11). Which means a refusal arrives here as a
    refusal -- an unavailable weekly slot, a slot with no opening inside the
    search bound, a student who already has lessons -- so the admin is told
    before there is a confirm button to press, not after.

    `size` is validated against the same price list `PackageRequest` enforces,
    so a preview cannot be taken for a size the POST would reject.
    """
    store.catch_up()
    return {"preview": store.preview_open_package(student_id, size)}


@router.get("/students/{student_id}/package/renew/preview")
def preview_student_package_renewal(student_id: int, size: PurchasableSize) -> dict:
    """The dates a top-up would append, appending nothing. Sibling of the above."""
    store.catch_up()
    return {"preview": store.preview_renew_package(student_id, size)}


@router.post("/students/{student_id}/pause")
def pause_student(student_id: int, body: PauseRequest) -> dict:
    return {"ok": True, "data": store.pause_student(student_id, body.weeks)}


@router.post("/students/{student_id}/resume")
def resume_student(student_id: int) -> dict:
    return {"ok": True, "data": store.resume_student(student_id)}


@router.post("/students/{student_id}/status")
def set_student_status(student_id: int, body: StatusRequest) -> dict:
    store.set_student_status(student_id, body.status)
    return {"ok": True}


@router.post("/packages/{package_id}/invoiced")
def mark_package_invoiced(package_id: int) -> dict:
    store.mark_invoiced(package_id)
    return {"ok": True}


@router.delete("/lessons/{lesson_id}")
def remove_lesson(lesson_id: int) -> dict:
    store.remove_lesson(lesson_id)
    return {"ok": True}


@router.post("/lessons/{lesson_id}/done")
def complete_lesson(lesson_id: int) -> dict:
    return {"ok": True, "data": store.complete_lesson(lesson_id)}


@router.post("/lessons/{lesson_id}/undo")
def uncomplete_lesson(lesson_id: int) -> dict:
    return {"ok": True, "data": store.uncomplete_lesson(lesson_id)}


@router.post("/move-requests/{request_id}/approve")
def approve_move_request(request_id: int) -> dict:
    # Settle the clock first, like every other handler that turns on a lesson's
    # current status. This one never did, which is how approving could still
    # move a lesson whose time had already passed simply because nothing had
    # read this studio's data since it started.
    store.catch_up()
    lesson = store.approve_lesson_move(request_id)
    return {"ok": True, "data": lesson}


@router.post("/move-requests/{request_id}/decline")
def decline_move_request(request_id: int, body: DeclineMoveRequestBody | None = None) -> dict:
    """Turn a move request down, with an optional reason for the student.

    The body is optional all the way down: no body, `{}` and `{"reason": null}`
    all mean "no reason given". The request itself comes back rather than a bare
    `{"ok": true}`, so the caller can show the declined state straight away
    without a second round trip to find out what it now says.
    """
    store.catch_up()
    reason = body.reason_or_none() if body is not None else None
    return {"ok": True, "data": store.decline_lesson_move(request_id, reason)}


@router.get("/alerts")
def list_alerts() -> dict:
    store.catch_up()
    move_alerts = [
        {
            "type": "moveRequest",
            "student": {"id": student.id, "name": student.name, "status": student.status},
            "lesson": lesson,
            "moveRequest": move_request,
        }
        for student, lesson, move_request in store.list_move_requests()
    ]
    invoice_alerts = [
        {
            "type": "invoice",
            "student": {"id": student.id, "name": student.name, "status": student.status},
            "package": package,
        }
        for student, package in store.list_alerts()
    ]
    return {"alerts": [*move_alerts, *invoice_alerts]}
