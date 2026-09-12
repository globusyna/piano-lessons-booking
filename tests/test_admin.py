from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.store import STUDIO_TZ, store


def test_week_and_availability_have_seed_data(client: TestClient, admin_headers: dict[str, str]) -> None:
    # Next week, not this one: how much of the current week is already behind us
    # depends on the weekday the suite runs on, and a lesson whose time has
    # passed is completed on read and leaves the calendar. Next week's seeded
    # lessons and the seeded blackout are always still ahead.
    today = datetime.now(STUDIO_TZ).date()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=1)
    week = client.get("/admin/api/week", params={"start": monday.isoformat()}, headers=admin_headers)
    availability = client.get("/admin/availability", headers=admin_headers)

    assert week.status_code == 200
    assert len(week.json()["days"]) == 5
    assert all(len(day["cells"]) == 7 for day in week.json()["days"])
    cells = [cell for day in week.json()["days"] for cell in day["cells"]]
    assert any(cell["type"] == "lesson" for cell in cells)
    assert any(cell["type"] == "blackout" for cell in cells)
    assert availability.status_code == 200
    assert availability.json()["hours"]["2"]
    assert availability.json()["blackouts"]


def test_availability_and_blackout_mutations(client: TestClient, admin_headers: dict[str, str]) -> None:
    changed = client.post(
        "/admin/availability", json={"day": 1, "times": ["16:15", "14:45"]}, headers=admin_headers
    )
    starts_at = datetime.now(STUDIO_TZ) + timedelta(days=10)
    added = client.post(
        "/admin/blackout",
        json={"startsAt": starts_at.isoformat(), "note": "Studio maintenance"},
        headers=admin_headers,
    )
    blackout_id = added.json()["data"]["id"]
    removed = client.delete(f"/admin/blackout/{blackout_id}", headers=admin_headers)

    assert changed.status_code == 200
    assert store.hours[1] == ["14:45", "16:15"]
    assert added.status_code == 200
    assert removed.status_code == 200
    assert blackout_id not in store.blackouts


def test_student_admin_lifecycle(client: TestClient, admin_headers: dict[str, str]) -> None:
    created = client.post(
        "/admin/students",
        json={"name": "New Student", "slotDay": 4, "slotTime": "15:30"},
        headers=admin_headers,
    )
    student = created.json()["data"]
    student_id = student["id"]

    assert created.status_code == 201
    assert len(student["token"]) > 20
    assert client.get(f"/admin/students/{student_id}", headers=admin_headers).status_code == 200
    assert client.post(
        f"/admin/students/{student_id}/slot",
        json={"slotDay": 5, "slotTime": "17:00"},
        headers=admin_headers,
    ).status_code == 200
    assert client.post(
        f"/admin/students/{student_id}/status",
        json={"status": "flagged"},
        headers=admin_headers,
    ).status_code == 200
    assert client.post(
        f"/admin/students/{student_id}/package", json={"size": 5}, headers=admin_headers
    ).status_code == 200
    detail = client.get(f"/admin/students/{student_id}", headers=admin_headers).json()
    assert detail["student"]["status"] == "flagged"
    assert detail["student"]["slotDay"] == 5
    assert len(detail["lessons"]) == 5


def test_alert_invoice_and_lesson_removal(client: TestClient, admin_headers: dict[str, str]) -> None:
    alerts = client.get("/admin/alerts", headers=admin_headers)
    # Jonas by name, not "the only invoice alert": completing lessons whose time
    # has passed can carry another seeded student's package to full as well.
    alert = next(
        item
        for item in alerts.json()["alerts"]
        if item["type"] == "invoice" and item["student"]["name"] == "Jonas Berg"
    )

    invoiced = client.post(
        f"/admin/packages/{alert['package']['id']}/invoiced", headers=admin_headers
    )
    assert invoiced.status_code == 200
    remaining = client.get("/admin/alerts", headers=admin_headers).json()["alerts"]
    assert all(item["student"]["name"] != "Jonas Berg" for item in remaining)

    lesson_id = client.get("/admin/students/1", headers=admin_headers).json()["lessons"][0]["id"]
    removed = client.delete(f"/admin/lessons/{lesson_id}", headers=admin_headers)
    missing = client.delete(f"/admin/lessons/{lesson_id}", headers=admin_headers)
    assert removed.status_code == 200
    assert missing.status_code == 404


def test_admin_calendar_shows_and_approves_move_request(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    view = client.get("/s/anna").json()
    lesson = next(item for item in view["lessons"] if item["canMove"])
    today = datetime.now(STUDIO_TZ).date()
    requested_slot = client.get(
        "/s/anna/slots",
        params={
            "from": today.isoformat(),
            "to": (today + timedelta(days=21)).isoformat(),
            "lessonId": lesson["id"],
        },
    ).json()["slots"][0]
    requested = client.post(
        f"/s/anna/lessons/{lesson['id']}/reschedule",
        json={"startsAt": requested_slot["startsAt"]},
    ).json()["data"]

    alerts = client.get("/admin/alerts", headers=admin_headers).json()["alerts"]
    move_alert = next(item for item in alerts if item["type"] == "moveRequest")
    assert move_alert["student"]["name"] == "Anna Lie"
    assert move_alert["lesson"]["id"] == lesson["id"]
    assert move_alert["moveRequest"] == requested

    original_date = datetime.fromisoformat(lesson["startsAt"]).astimezone(STUDIO_TZ).date()
    monday = original_date - timedelta(days=original_date.weekday())
    week = client.get(
        "/admin/api/week", params={"start": monday.isoformat()}, headers=admin_headers
    ).json()
    cell = next(
        cell
        for day in week["days"]
        for cell in day["cells"]
        if cell.get("lessonId") == lesson["id"]
    )
    assert cell["moveRequest"]["requestedStartsAt"] == requested_slot["startsAt"]

    approved = client.post(
        f"/admin/move-requests/{requested['id']}/approve", headers=admin_headers
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["startsAt"] == requested_slot["startsAt"]
    remaining_alerts = client.get("/admin/alerts", headers=admin_headers).json()["alerts"]
    assert all(item["type"] != "moveRequest" for item in remaining_alerts)
    refreshed = client.get("/s/anna").json()
    moved_lesson = next(item for item in refreshed["lessons"] if item["id"] == lesson["id"])
    assert moved_lesson["requestedStartsAt"] is None
