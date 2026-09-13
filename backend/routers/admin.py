from datetime import date, timedelta

from fastapi import APIRouter, Depends

from ..auth import require_admin
from ..models import (
    AvailabilityRequest,
    BlackoutRequest,
    PackageRequest,
    PauseRequest,
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
    lesson = store.approve_lesson_move(request_id)
    return {"ok": True, "data": lesson}


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
