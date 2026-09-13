"""Pausing a student for 1-6 weeks, and what happens to their lessons.

A pause is a shift, not a flag: every still-scheduled lesson moves forward by
the length of the break, which is what actually frees the weekly slot. These
tests go at that through the endpoints, and read the resulting lesson times back
rather than trusting the status column.

Time is pinned with `clock.pinned(...)` from `backend.store` -- the same seam
lesson completion uses -- because the instants that matter (a break running out,
a shifted lesson falling due) are weeks away and cannot be waited for. Two tests
read `student_pauses` through the store's own session: `ended_early_at` is what
separates a break that ran out from one the teacher ended, and no endpoint
exposes it.
"""

from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.db_models import StudentPauseRecord
from backend.store import STUDIO_TZ, clock, store


def _create_student(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    slot_day: int,
    slot_time: str,
    size: int = 10,
) -> dict:
    """A student with `size` scheduled lessons on their weekly slot, all ahead."""
    created = client.post(
        "/admin/students",
        json={"name": name, "slotDay": slot_day, "slotTime": slot_time},
        headers=admin_headers,
    )
    assert created.status_code == 201
    student_id = created.json()["data"]["id"]
    opened = client.post(
        f"/admin/students/{student_id}/package", json={"size": size}, headers=admin_headers
    )
    assert opened.status_code == 200
    return {
        "id": student_id,
        "token": created.json()["data"]["token"],
        "lessons": _lessons(client, admin_headers, student_id),
    }


def _lessons(client: TestClient, admin_headers: dict[str, str], student_id: int) -> list[dict]:
    response = client.get(f"/admin/students/{student_id}", headers=admin_headers)
    assert response.status_code == 200
    return response.json()["lessons"]


def _student(client: TestClient, admin_headers: dict[str, str], student_id: int) -> dict:
    response = client.get(f"/admin/students/{student_id}", headers=admin_headers)
    assert response.status_code == 200
    return response.json()["student"]


def _starts_at(lesson: dict) -> datetime:
    return datetime.fromisoformat(lesson["startsAt"]).astimezone(STUDIO_TZ)


def _times(lessons: list[dict]) -> list[datetime]:
    return sorted(_starts_at(lesson) for lesson in lessons)


def _today() -> date:
    return datetime.now(STUDIO_TZ).date()


def test_a_pause_moves_every_upcoming_lesson_forward_by_the_same_weeks(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Shift Pupil", 1, "14:45", size=5)
    before = _times(student["lessons"])

    response = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
    )

    assert response.status_code == 200
    after_student = _student(client, admin_headers, student["id"])
    after_lessons = _lessons(client, admin_headers, student["id"])
    assert after_student["status"] == "paused"
    assert after_student["pausedUntil"] == (_today() + timedelta(weeks=2)).isoformat()
    assert _times(after_lessons) == [moment + timedelta(weeks=2) for moment in before]
    assert [lesson["seq"] for lesson in after_lessons] == [1, 2, 3, 4, 5]
    assert after_student["pkg"]["used"] == 0


def test_the_weeks_a_pause_covers_are_immediately_open_to_anyone_else(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Slot Pupil", 1, "14:45", size=5)
    other = _create_student(client, admin_headers, "Other Pupil", 3, "15:30", size=5)
    vacated = _starts_at(student["lessons"][0])

    paused = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 1}, headers=admin_headers
    )

    assert paused.status_code == 200
    monday = vacated.date() - timedelta(days=vacated.weekday())
    week = client.get(
        "/admin/api/week", params={"start": monday.isoformat()}, headers=admin_headers
    ).json()
    cells = [cell for day in week["days"] for cell in day["cells"]]
    vacated_cell = next(
        cell for cell in cells if datetime.fromisoformat(cell["startsAt"]) == vacated
    )
    slots = client.get(
        f"/s/{other['token']}/slots",
        params={"from": _today().isoformat(), "to": (_today() + timedelta(days=21)).isoformat()},
    ).json()["slots"]
    assert vacated_cell["type"] == "open"
    assert vacated.isoformat() in [
        datetime.fromisoformat(slot["startsAt"]).isoformat() for slot in slots
    ]


def test_the_shifted_lessons_show_on_the_week_they_moved_to(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Week View", 1, "14:45", size=5)
    first = _starts_at(student["lessons"][0])

    paused = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 1}, headers=admin_headers
    )

    assert paused.status_code == 200
    moved_to = first + timedelta(weeks=1)
    monday = moved_to.date() - timedelta(days=moved_to.weekday())
    week = client.get(
        "/admin/api/week", params={"start": monday.isoformat()}, headers=admin_headers
    ).json()
    cells = [cell for day in week["days"] for cell in day["cells"]]
    moved_cell = next(
        cell for cell in cells if datetime.fromisoformat(cell["startsAt"]) == moved_to
    )
    assert moved_cell["type"] == "lesson"
    assert moved_cell["studentName"] == "Week View"
    assert moved_cell["seq"] == 1


@pytest.mark.parametrize("weeks", [0, -2, 7, 2.5, "three", None])
def test_a_break_is_a_whole_number_of_weeks_from_one_to_six(
    client: TestClient, admin_headers: dict[str, str], weeks: object
) -> None:
    student = _create_student(client, admin_headers, "Length Pupil", 1, "14:45", size=5)
    before = _times(student["lessons"])

    response = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": weeks}, headers=admin_headers
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PAUSE_LENGTH"
    assert _student(client, admin_headers, student["id"])["status"] == "active"
    assert _times(_lessons(client, admin_headers, student["id"])) == before


def test_pausing_a_student_who_is_already_paused_changes_nothing(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Twice Pupil", 1, "14:45", size=5)
    first = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
    )
    assert first.status_code == 200
    after_first = _times(_lessons(client, admin_headers, student["id"]))

    response = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 3}, headers=admin_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "STUDENT_PAUSED"
    assert _student(client, admin_headers, student["id"])["pausedUntil"] == (
        _today() + timedelta(weeks=2)
    ).isoformat()
    assert _times(_lessons(client, admin_headers, student["id"])) == after_first


def test_a_flagged_student_cannot_be_paused(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Flagged Pupil", 1, "14:45", size=5)
    before = _times(student["lessons"])
    flagged = client.post(
        f"/admin/students/{student['id']}/status",
        json={"status": "flagged"},
        headers=admin_headers,
    )
    assert flagged.status_code == 200

    response = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "STUDENT_FLAGGED"
    assert _student(client, admin_headers, student["id"])["status"] == "flagged"
    assert _times(_lessons(client, admin_headers, student["id"])) == before


def test_a_pending_move_request_has_to_be_answered_before_a_pause(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Pending Pupil", 1, "14:45", size=5)
    before = _times(student["lessons"])
    # Not the first lesson: within 48 hours of it, a move cannot be requested at
    # all, and this test needs a pending request rather than a refused one.
    lesson = student["lessons"][1]
    slot = client.get(
        f"/s/{student['token']}/slots",
        params={
            "from": _today().isoformat(),
            "to": (_today() + timedelta(days=21)).isoformat(),
            "lessonId": lesson["id"],
        },
    ).json()["slots"][0]
    requested = client.post(
        f"/s/{student['token']}/lessons/{lesson['id']}/reschedule",
        json={"startsAt": slot["startsAt"]},
    )
    assert requested.status_code == 200

    response = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MOVE_REQUEST_PENDING"
    assert _student(client, admin_headers, student["id"])["status"] == "active"
    assert _times(_lessons(client, admin_headers, student["id"])) == before
    alerts = client.get("/admin/alerts", headers=admin_headers).json()["alerts"]
    assert [alert["type"] for alert in alerts if alert["student"]["id"] == student["id"]] == [
        "moveRequest"
    ]


def test_a_pause_that_would_land_on_a_taken_time_is_refused_whole(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The shift is all or nothing: no lesson is left half-moved.

    The collision is built the only way the API allows: a hole is made in one
    student's weekly run, and another student's lesson is moved into it. Pausing
    then tries to put a lesson exactly there.
    """
    student = _create_student(client, admin_headers, "Collide Pupil", 1, "14:45", size=5)
    neighbour = _create_student(client, admin_headers, "Neighbour Pupil", 2, "14:45", size=5)
    third_week = student["lessons"][2]
    removed = client.delete(f"/admin/lessons/{third_week['id']}", headers=admin_headers)
    assert removed.status_code == 200
    contested = _starts_at(third_week)
    requested = client.post(
        f"/s/{neighbour['token']}/lessons/{neighbour['lessons'][1]['id']}/reschedule",
        json={"startsAt": contested.isoformat()},
    )
    assert requested.status_code == 200, requested.json()
    approved = client.post(
        f"/admin/move-requests/{requested.json()['data']['id']}/approve", headers=admin_headers
    )
    assert approved.status_code == 200
    before = _times(_lessons(client, admin_headers, student["id"]))

    response = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SLOT_TAKEN"
    assert _student(client, admin_headers, student["id"])["status"] == "active"
    assert _times(_lessons(client, admin_headers, student["id"])) == before
    assert contested in _times(_lessons(client, admin_headers, neighbour["id"]))


def test_resuming_early_leaves_the_lessons_where_the_pause_put_them(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Early Pupil", 1, "14:45", size=5)
    paused = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 3}, headers=admin_headers
    )
    assert paused.status_code == 200
    shifted = _times(_lessons(client, admin_headers, student["id"]))

    response = client.post(
        f"/admin/students/{student['id']}/resume", headers=admin_headers
    )
    repeated = client.post(f"/admin/students/{student['id']}/resume", headers=admin_headers)

    assert response.status_code == 200
    after = _student(client, admin_headers, student["id"])
    assert after["status"] == "active"
    assert after["pausedUntil"] is None
    # The original times are not reclaimed even though nothing else took them.
    assert _times(_lessons(client, admin_headers, student["id"])) == shifted
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "STUDENT_NOT_PAUSED"
    with store._sessions.begin() as session:
        row = session.scalars(
            select(StudentPauseRecord).where(StudentPauseRecord.student_id == student["id"])
        ).one()
        assert row.weeks == 3
        assert row.starts_on == _today()
        assert row.ends_on == _today() + timedelta(weeks=3)
        assert row.ended_early_at is not None


def test_resuming_a_student_who_is_not_paused_is_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Active Pupil", 1, "14:45", size=5)

    response = client.post(f"/admin/students/{student['id']}/resume", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STUDENT_NOT_PAUSED"
    assert _student(client, admin_headers, student["id"])["status"] == "active"


def test_a_break_ends_by_itself_once_its_last_week_has_passed(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Expiry Pupil", 1, "14:45", size=5)
    paused = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 1}, headers=admin_headers
    )
    assert paused.status_code == 200
    ends_on = date.fromisoformat(paused.json()["data"]["pausedUntil"])
    shifted = _times(_lessons(client, admin_headers, student["id"]))

    # Morning of the return date, before any lesson of the day could fall due.
    with clock.pinned(datetime.combine(ends_on, time(9, 0), STUDIO_TZ)):
        view = client.get(f"/s/{student['token']}").json()
        after = _student(client, admin_headers, student["id"])
        lessons = _times(_lessons(client, admin_headers, student["id"]))

    assert view["student"]["status"] == "active"
    assert view["pausedUntil"] is None
    assert after["status"] == "active"
    assert after["pkg"]["used"] == 0
    # Expiry lifts the status and nothing else -- the shift already happened.
    assert lessons == shifted
    with store._sessions.begin() as session:
        row = session.scalars(
            select(StudentPauseRecord).where(StudentPauseRecord.student_id == student["id"])
        ).one()
        assert row.ended_early_at is None


def test_a_break_is_still_on_the_day_before_it_ends(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Last Day", 1, "14:45", size=5)
    paused = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
    )
    assert paused.status_code == 200
    ends_on = date.fromisoformat(paused.json()["data"]["pausedUntil"])

    with clock.pinned(datetime.combine(ends_on - timedelta(days=1), time(23, 0), STUDIO_TZ)):
        view = client.get(f"/s/{student['token']}").json()

    assert view["student"]["status"] == "paused"
    assert view["pausedUntil"] == ends_on.isoformat()
    assert view["canRequestPause"] is False


def test_a_paused_students_lesson_completes_and_consumes_the_package(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Completion is decided by the lesson, never by the student's status.

    The shifted lesson falls due after the break has expired, because a pause
    moves every lesson past `ends_on` by construction. What matters is that the
    sweep treats it like any other lesson when its time comes.
    """
    student = _create_student(client, admin_headers, "Sweep Pupil", 1, "14:45", size=5)
    paused = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
    )
    assert paused.status_code == 200
    shifted = _lessons(client, admin_headers, student["id"])
    first = next(lesson for lesson in shifted if lesson["status"] == "scheduled")

    with clock.pinned(_starts_at(first)):
        after = client.get(f"/admin/students/{student['id']}", headers=admin_headers).json()

    assert after["student"]["pkg"]["used"] == 1
    assert next(item for item in after["lessons"] if item["id"] == first["id"])["status"] == "done"


def test_a_pause_never_leaves_a_lesson_behind_in_the_past(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """A pause must not hand the sweep a lesson that instantly consumes a credit.

    Lessons whose time has already passed are completed before the shift, not
    dragged forward, and everything the shift moves lands in the future. So the
    package is consumed by exactly the lessons that had already happened, and a
    second read right afterwards consumes nothing more.
    """
    student = _create_student(client, admin_headers, "Overdue Pupil", 1, "14:45", size=5)
    third = _starts_at(student["lessons"][2])

    with clock.pinned(third):
        paused = client.post(
            f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
        )
        after = client.get(f"/admin/students/{student['id']}", headers=admin_headers).json()
        again = client.get(f"/admin/students/{student['id']}", headers=admin_headers).json()

    assert paused.status_code == 200
    assert after["student"]["pkg"]["used"] == 3
    assert again["student"]["pkg"]["used"] == 3
    still_scheduled = [item for item in after["lessons"] if item["status"] == "scheduled"]
    assert len(still_scheduled) == 2
    assert all(_starts_at(item) > third for item in still_scheduled)


def test_pausing_a_student_whose_package_is_finished_succeeds(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The package boundary: nothing is left to shift, and that is not an error."""
    student = _create_student(client, admin_headers, "Boundary Pupil", 1, "14:45", size=5)
    last = _starts_at(student["lessons"][-1])
    with clock.pinned(last):
        consumed = client.get(f"/admin/students/{student['id']}", headers=admin_headers).json()
    assert consumed["student"]["pkg"]["used"] == 5
    before = _times(consumed["lessons"])

    response = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 4}, headers=admin_headers
    )

    assert response.status_code == 200
    after = _student(client, admin_headers, student["id"])
    assert after["status"] == "paused"
    assert after["pausedUntil"] == (_today() + timedelta(weeks=4)).isoformat()
    assert after["pkg"]["used"] == 5
    assert _times(_lessons(client, admin_headers, student["id"])) == before


def test_the_status_endpoint_is_not_a_second_way_into_a_pause(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Status Pupil", 1, "14:45", size=5)
    before = _times(student["lessons"])

    response = client.post(
        f"/admin/students/{student['id']}/status", json={"status": "paused"}, headers=admin_headers
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "USE_PAUSE_ENDPOINT"
    assert _student(client, admin_headers, student["id"])["status"] == "active"
    assert _times(_lessons(client, admin_headers, student["id"])) == before


def test_a_paused_student_can_still_be_flagged_and_unflagged(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Flag While Paused", 1, "14:45", size=5)
    paused = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
    )
    assert paused.status_code == 200

    flagged = client.post(
        f"/admin/students/{student['id']}/status",
        json={"status": "flagged"},
        headers=admin_headers,
    )
    unflagged = client.post(
        f"/admin/students/{student['id']}/status",
        json={"status": "active"},
        headers=admin_headers,
    )

    assert flagged.status_code == 200
    assert unflagged.status_code == 200
    assert _student(client, admin_headers, student["id"])["status"] == "active"


def test_a_student_asks_for_a_break_of_a_chosen_length(client: TestClient) -> None:
    response = client.post("/s/anna/pause-request", json={"weeks": 6})

    assert response.status_code == 200
    view = client.get("/s/anna").json()
    assert view["student"]["status"] == "paused"
    assert view["pausedUntil"] == (_today() + timedelta(weeks=6)).isoformat()
    assert view["canRequestPause"] is False


def test_a_student_cannot_ask_for_a_break_longer_than_six_weeks(client: TestClient) -> None:
    response = client.post("/s/anna/pause-request", json={"weeks": 8})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PAUSE_LENGTH"
    assert client.get("/s/anna").json()["student"]["status"] == "active"
