"""Lessons complete when their time passes, and packages consume as they do.

Time here is pinned with `clock.pinned(...)` from `backend.store` rather than
waited for: the interesting instants are weeks away. Pinning only changes what
the completion logic reads as "now", so an unpinned read afterwards never undoes
what a pinned one completed.

A few tests reach into the store's session to build a package state the API
cannot produce -- a package already at `used == size` with a lesson still
scheduled. That state is exactly what the `used <= size` CHECK constraint and
the undo guard exist for, so it has to be constructed to be tested at all.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.db_models import PackageRecord
from backend.store import STUDIO_TZ, clock, store


def _create_student(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    slot_day: int,
    slot_time: str,
    size: int = 10,
) -> dict:
    """A student with a package of `size` scheduled lessons, all still ahead."""
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
    detail = client.get(f"/admin/students/{student_id}", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    return {
        "id": student_id,
        "token": created.json()["data"]["token"],
        "package_id": body["student"]["pkg"]["id"],
        "lessons": body["lessons"],
    }


def _starts_at(lesson: dict) -> datetime:
    return datetime.fromisoformat(lesson["startsAt"]).astimezone(STUDIO_TZ)


def _package(client: TestClient, admin_headers: dict[str, str], student_id: int) -> dict:
    return client.get(f"/admin/students/{student_id}", headers=admin_headers).json()["student"][
        "pkg"
    ]


@pytest.mark.parametrize(
    "read",
    ["admin_students", "admin_student", "admin_week", "admin_alerts", "student_page"],
)
def test_every_read_endpoint_completes_a_lesson_whose_time_has_passed(
    client: TestClient, admin_headers: dict[str, str], read: str
) -> None:
    student = _create_student(client, admin_headers, "Read Sweep", 1, "14:45")
    first = _starts_at(student["lessons"][0])
    monday = (first.date() - timedelta(days=first.weekday())).isoformat()
    requests = {
        "admin_students": lambda: client.get("/admin/students", headers=admin_headers),
        "admin_student": lambda: client.get(
            f"/admin/students/{student['id']}", headers=admin_headers
        ),
        "admin_week": lambda: client.get(
            "/admin/api/week", params={"start": monday}, headers=admin_headers
        ),
        "admin_alerts": lambda: client.get("/admin/alerts", headers=admin_headers),
        "student_page": lambda: client.get(f"/s/{student['token']}"),
    }

    with clock.pinned(first):
        response = requests[read]()

    assert response.status_code == 200
    # Read through the store, not a second endpoint: every endpoint under test
    # here completes lessons itself, so asking one of them would prove nothing
    # about the one being exercised.
    assert store.student(student["id"]).pkg.used == 1
    assert store.lesson(student["lessons"][0]["id"]).status.value == "done"


def test_package_fills_at_the_instant_its_last_lesson_starts(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Boundary", 1, "16:15", size=10)
    last = _starts_at(student["lessons"][-1])

    with clock.pinned(last - timedelta(seconds=1)):
        before = _package(client, admin_headers, student["id"])
        alerts_before = client.get("/admin/alerts", headers=admin_headers).json()["alerts"]

    with clock.pinned(last):
        after = client.get(f"/admin/students/{student['id']}", headers=admin_headers).json()
        alerts_after = client.get("/admin/alerts", headers=admin_headers).json()["alerts"]

    assert before["used"] == 9
    assert before["size"] == 10
    assert not [
        alert
        for alert in alerts_before
        if alert["type"] == "invoice" and alert["student"]["id"] == student["id"]
    ]
    assert after["student"]["pkg"]["used"] == 10
    assert after["student"]["invoiceSent"] is False
    assert [
        alert
        for alert in alerts_after
        if alert["type"] == "invoice" and alert["package"]["id"] == student["package_id"]
    ]


def test_a_lesson_is_counted_once_however_often_completion_runs(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Twice", 1, "17:00")
    first = _starts_at(student["lessons"][0])

    with clock.pinned(first):
        # Straight at the completion logic, twice, the way two overlapping
        # requests would reach it.
        first_sweep = store.complete_due_lessons()
        second_sweep = store.complete_due_lessons()
        after_sweeps = _package(client, admin_headers, student["id"])
        repeated_read = _package(client, admin_headers, student["id"])

    assert first_sweep >= 1
    assert second_sweep == 0
    assert after_sweeps["used"] == 1
    assert repeated_read["used"] == 1


def test_a_full_package_completes_the_lesson_without_counting_it(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Already Full", 1, "17:45", size=5)
    lesson = student["lessons"][0]
    with store._sessions.begin() as session:
        package = session.get(PackageRecord, student["package_id"])
        assert package is not None
        package.used = package.size

    with clock.pinned(_starts_at(lesson)):
        detail = client.get(f"/admin/students/{student['id']}", headers=admin_headers)

    assert detail.status_code == 200
    body = detail.json()
    assert body["student"]["pkg"]["used"] == 5
    assert next(item for item in body["lessons"] if item["id"] == lesson["id"])["status"] == "done"


def test_paused_and_flagged_students_lessons_complete_like_everyone_elses(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    paused = _create_student(client, admin_headers, "Paused Pupil", 1, "14:45")
    flagged = _create_student(client, admin_headers, "Flagged Pupil", 1, "16:15")
    for student, status in ((paused, "paused"), (flagged, "flagged")):
        changed = client.post(
            f"/admin/students/{student['id']}/status",
            json={"status": status},
            headers=admin_headers,
        )
        assert changed.status_code == 200
    latest = max(_starts_at(paused["lessons"][0]), _starts_at(flagged["lessons"][0]))

    with clock.pinned(latest):
        students = client.get("/admin/students", headers=admin_headers).json()["students"]

    by_id = {item["id"]: item for item in students}
    assert by_id[paused["id"]]["status"] == "paused"
    assert by_id[paused["id"]]["pkg"]["used"] == 1
    assert by_id[flagged["id"]]["status"] == "flagged"
    assert by_id[flagged["id"]]["pkg"]["used"] == 1


def test_a_deleted_lesson_is_never_completed(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Deleted Lesson", 1, "18:30")
    lesson = student["lessons"][0]
    removed = client.delete(f"/admin/lessons/{lesson['id']}", headers=admin_headers)

    with clock.pinned(_starts_at(lesson)):
        detail = client.get(f"/admin/students/{student['id']}", headers=admin_headers).json()

    assert removed.status_code == 200
    assert lesson["id"] not in [item["id"] for item in detail["lessons"]]
    assert detail["student"]["pkg"]["used"] == 0


def test_admin_marks_a_future_lesson_done(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Early Finish", 1, "14:45")
    future = student["lessons"][-1]

    response = client.post(f"/admin/lessons/{future['id']}/done", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "done"
    assert _starts_at(future) > datetime.now(STUDIO_TZ)
    assert _package(client, admin_headers, student["id"])["used"] == 1


def test_marking_an_already_done_lesson_done_is_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Done Twice", 1, "15:30")
    lesson = student["lessons"][0]
    client.post(f"/admin/lessons/{lesson['id']}/done", headers=admin_headers)

    repeated = client.post(f"/admin/lessons/{lesson['id']}/done", headers=admin_headers)

    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "LESSON_ALREADY_DONE"
    assert _package(client, admin_headers, student["id"])["used"] == 1


def test_marking_a_lesson_done_on_a_full_package_is_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "No Room Left", 1, "16:15", size=5)
    with store._sessions.begin() as session:
        package = session.get(PackageRecord, student["package_id"])
        assert package is not None
        package.used = package.size

    response = client.post(
        f"/admin/lessons/{student['lessons'][0]['id']}/done", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PACKAGE_FULL"
    assert _package(client, admin_headers, student["id"])["used"] == 5


def test_admin_undoes_a_completed_lesson(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Undone", 1, "17:00")
    lesson = student["lessons"][-1]
    client.post(f"/admin/lessons/{lesson['id']}/done", headers=admin_headers)

    undone = client.post(f"/admin/lessons/{lesson['id']}/undo", headers=admin_headers)

    assert undone.status_code == 200
    assert undone.json()["data"]["status"] == "scheduled"
    assert _package(client, admin_headers, student["id"])["used"] == 0


def test_undoing_a_scheduled_lesson_is_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Never Done", 1, "17:45")

    response = client.post(
        f"/admin/lessons/{student['lessons'][-1]['id']}/undo", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LESSON_NOT_DONE"
    assert _package(client, admin_headers, student["id"])["used"] == 0


def test_undoing_against_an_empty_package_is_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Nothing To Give Back", 1, "18:30")
    lesson = student["lessons"][-1]
    client.post(f"/admin/lessons/{lesson['id']}/done", headers=admin_headers)
    # A done lesson against a package counting zero used lessons is not a state
    # the API can reach; the guard exists so a bad row cannot be made worse.
    with store._sessions.begin() as session:
        package = session.get(PackageRecord, student["package_id"])
        assert package is not None
        package.used = 0

    response = client.post(f"/admin/lessons/{lesson['id']}/undo", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PACKAGE_EMPTY"
    assert _package(client, admin_headers, student["id"])["used"] == 0


def test_undoing_a_past_lesson_lets_the_next_read_complete_it_again(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Expected behaviour, not a bug: completion is derived from the clock.

    Keeping a past lesson out of the sweep takes "undo, then delete". A
    first-class cancelled status that would not need the two-step is #44.
    """
    student = _create_student(client, admin_headers, "Back Again", 1, "14:45")
    lesson = student["lessons"][0]

    with clock.pinned(_starts_at(lesson)):
        swept = _package(client, admin_headers, student["id"])
        undone = client.post(f"/admin/lessons/{lesson['id']}/undo", headers=admin_headers)
        after_undo = store.student(student["id"]).pkg.used
        reread = client.get(f"/admin/students/{student['id']}", headers=admin_headers).json()

    assert swept["used"] == 1
    assert undone.status_code == 200
    assert undone.json()["data"]["status"] == "scheduled"
    assert after_undo == 0
    assert next(item for item in reread["lessons"] if item["id"] == lesson["id"])["status"] == "done"
    assert reread["student"]["pkg"]["used"] == 1


def test_seeded_students_are_swept_on_the_same_terms_as_anyone_else(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """No code path exempts the demo studio -- that gap is what #9 is about."""
    far_ahead = datetime.now(STUDIO_TZ) + timedelta(weeks=20)

    with clock.pinned(far_ahead):
        students = client.get("/admin/students", headers=admin_headers).json()["students"]
        alerts = client.get("/admin/alerts", headers=admin_headers).json()["alerts"]

    seeded = {student["name"]: student for student in students}
    invoiced_names = {
        alert["student"]["name"] for alert in alerts if alert["type"] == "invoice"
    }
    assert set(seeded) >= {
        "Anna Lie",
        "Jonas Berg",
        "Mira Solheim",
        "Teodor Haugen",
        "Selma Ruud",
        "Oskar Dahl",
    }
    assert all(
        student["pkg"]["used"] == student["pkg"]["size"] for student in seeded.values()
    )
    assert {"Mira Solheim", "Teodor Haugen"} <= invoiced_names
    assert not [
        lesson for lesson in store.lessons.values() if lesson.status.value == "scheduled"
    ]
