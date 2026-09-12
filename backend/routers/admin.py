from datetime import date, timedelta

from fastapi import APIRouter, Depends

from ..auth import require_admin
from ..models import (
    AvailabilityRequest,
    BlackoutRequest,
    PackageRequest,
    StatusRequest,
    StudentCreate,
    StudentSlotRequest,
)
from ..store import ROW_TIMES, StoreError, store


router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("/api/week")
def get_week(start: date) -> dict:
    if start.weekday() != 0:
        raise StoreError(400, "INVALID_WEEK", "The requested week must start on Monday.")
    days = []
    for offset in range(5):
        day_date = start + timedelta(days=offset)
        cells = []
        for local_time in ROW_TIMES:
            starts_at = store._at(day_date, local_time)
            lesson = next(
                (
                    item
                    for item in store.lessons.values()
                    if item.starts_at == starts_at and item.status.value == "scheduled"
                ),
                None,
            )
            blackout = next(
                (item for item in store.blackouts.values() if item.starts_at == starts_at), None
            )
            if lesson:
                student = store.student(lesson.student_id)
                cells.append(
                    {
                        "type": "lesson",
                        "startsAt": starts_at,
                        "lessonId": lesson.id,
                        "studentName": student.name,
                        "seq": lesson.seq,
                        "size": student.pkg.size,
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
        "blackouts": [
            {"id": item.id, "startsAt": item.starts_at, "note": item.note}
            for item in sorted(store.blackouts.values(), key=lambda value: value.starts_at)
        ],
    }


@router.post("/availability")
def set_availability(body: AvailabilityRequest) -> dict:
    store.hours[body.day] = body.times
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
    return {"students": list(store.students.values())}


@router.post("/students", status_code=201)
def create_student(body: StudentCreate) -> dict:
    return {
        "ok": True,
        "data": store.create_student(body.name, body.slot_day, body.slot_time),
    }


@router.get("/students/{student_id}")
def get_student(student_id: int) -> dict:
    return {"student": store.student(student_id), "lessons": store.lesson_history(student_id)}


@router.post("/students/{student_id}/slot")
def set_student_slot(student_id: int, body: StudentSlotRequest) -> dict:
    student = store.student(student_id)
    student.slot_day = body.slot_day
    student.slot_time = body.slot_time
    return {"ok": True}


@router.post("/students/{student_id}/package")
def open_student_package(student_id: int, body: PackageRequest) -> dict:
    store.open_package(student_id, body.size)
    return {"ok": True}


@router.post("/students/{student_id}/status")
def set_student_status(student_id: int, body: StatusRequest) -> dict:
    store.student(student_id).status = body.status
    return {"ok": True}


@router.post("/packages/{package_id}/invoiced")
def mark_package_invoiced(package_id: int) -> dict:
    store.mark_invoiced(package_id)
    return {"ok": True}


@router.delete("/lessons/{lesson_id}")
def remove_lesson(lesson_id: int) -> dict:
    if store.lessons.pop(lesson_id, None) is None:
        raise StoreError(404, "NOT_FOUND", "Lesson not found.")
    return {"ok": True}


@router.get("/alerts")
def list_alerts() -> dict:
    alerts = [
        {
            "student": {"id": student.id, "name": student.name, "status": student.status},
            "package": student.pkg,
        }
        for student in store.students.values()
        if student.pkg.used >= student.pkg.size and not student.invoice_sent
    ]
    return {"alerts": alerts}
