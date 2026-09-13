"""Renewing a package by topping up the lessons already available.

A renewal extends the package that is there rather than starting a new one:
`size` goes up, `used` and `period_no` stay, no scheduled lesson moves, and the
bought lessons are appended to the end of the run. These tests read the lesson
dates back through the endpoints rather than trusting the counters.

Time is pinned with `clock.pinned(...)` from `backend.store` -- #9's seam, the
same one `test_completion.py` and `test_pause.py` use -- wherever a package has
to be carried to `used == size` first. The instant its last lesson falls due is
weeks out and cannot be waited for. Every date here is derived from the lessons
the API hands back, never written down.

The seeded studio holds 15:30 on Monday, 16:15 and 18:30 on Tuesday, 17:00 on
Wednesday, 14:45 on Thursday and 17:45 on Friday. Students made here take 14:00,
which is free on every day, because `lessons.starts_at` is unique across the
whole studio and a clash would be a slot collision rather than the behaviour
under test.
"""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.db_models import PackageRecord
from backend.store import STUDIO_TZ, clock, store


def _create_student(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    slot_day: int,
    slot_time: str = "14:00",
    size: int | None = 10,
) -> int:
    """A student whose package holds `size` scheduled lessons, all still ahead.

    `size=None` leaves the package the student was created with: a real row with
    no lessons behind it, which is the state a renewal has to fall back from.
    """
    created = client.post(
        "/admin/students",
        json={"name": name, "slotDay": slot_day, "slotTime": slot_time},
        headers=admin_headers,
    )
    assert created.status_code == 201
    student_id = created.json()["data"]["id"]
    if size is not None:
        opened = client.post(
            f"/admin/students/{student_id}/package",
            json={"size": size},
            headers=admin_headers,
        )
        assert opened.status_code == 200
    return student_id


def _detail(client: TestClient, admin_headers: dict[str, str], student_id: int) -> dict:
    response = client.get(f"/admin/students/{student_id}", headers=admin_headers)
    assert response.status_code == 200
    return response.json()


def _renew(
    client: TestClient, admin_headers: dict[str, str], student_id: int, size: int
) -> object:
    return client.post(
        f"/admin/students/{student_id}/package/renew", json={"size": size}, headers=admin_headers
    )


def _starts_at(lesson: dict) -> datetime:
    return datetime.fromisoformat(lesson["startsAt"]).astimezone(STUDIO_TZ)


def _times(lessons: list[dict]) -> list[datetime]:
    return sorted(_starts_at(lesson) for lesson in lessons)


def _finish_the_package(
    client: TestClient, admin_headers: dict[str, str], student_id: int
) -> None:
    """Carry the package to `used == size` by letting every lesson fall due."""
    lessons = _detail(client, admin_headers, student_id)["lessons"]
    with clock.pinned(max(_times(lessons)) + timedelta(hours=1)):
        client.get(f"/admin/students/{student_id}", headers=admin_headers)


def _package_rows(student_id: int) -> int:
    """How many `packages` rows this student has.

    Read off the table because the point is that a row is *not* created, and the
    API only ever shows the current package -- a second one would be invisible
    through it until the first was finished.
    """
    with store._sessions() as session:
        return session.scalar(
            select(func.count())
            .select_from(PackageRecord)
            .where(PackageRecord.student_id == student_id)
        )


def test_renewing_adds_the_bought_lessons_to_the_end_of_the_schedule(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student_id = _create_student(client, admin_headers, "Five More", 2, size=5)
    before = _detail(client, admin_headers, student_id)
    last_before = max(_times(before["lessons"]))

    renewed = _renew(client, admin_headers, student_id, 5)
    after = _detail(client, admin_headers, student_id)

    assert renewed.status_code == 200
    assert renewed.json() == {"ok": True}
    assert after["student"]["pkg"]["size"] == 10
    assert after["student"]["pkg"]["used"] == before["student"]["pkg"]["used"]
    assert after["student"]["pkg"]["periodNo"] == before["student"]["pkg"]["periodNo"]
    assert [lesson["seq"] for lesson in after["lessons"]] == list(range(1, 11))
    assert _times(after["lessons"])[:5] == _times(before["lessons"])
    assert _times(after["lessons"])[5:] == [
        last_before + timedelta(weeks=week) for week in range(1, 6)
    ]


def test_renewing_a_ten_by_ten_makes_a_package_of_twenty(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student_id = _create_student(client, admin_headers, "Twenty Total", 3, size=10)

    renewed = _renew(client, admin_headers, student_id, 10)
    after = _detail(client, admin_headers, student_id)

    assert renewed.status_code == 200
    assert after["student"]["pkg"]["size"] == 20
    assert len(after["lessons"]) == 20
    assert [lesson["seq"] for lesson in after["lessons"]] == list(range(1, 21))


def test_renewing_a_mid_flight_package_leaves_the_lessons_it_already_has(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student_id = _create_student(client, admin_headers, "Half Way", 4, size=10)
    lessons = _detail(client, admin_headers, student_id)["lessons"]
    with clock.pinned(_times(lessons)[2] + timedelta(hours=1)):
        client.get(f"/admin/students/{student_id}", headers=admin_headers)
    before = _detail(client, admin_headers, student_id)

    renewed = _renew(client, admin_headers, student_id, 5)
    after = _detail(client, admin_headers, student_id)

    assert renewed.status_code == 200
    assert before["student"]["pkg"]["used"] == 3
    assert after["student"]["pkg"] == {**before["student"]["pkg"], "size": 15}
    # Not one existing lesson moved or changed status.
    assert {lesson["id"]: (lesson["startsAt"], lesson["status"]) for lesson in after["lessons"]} | {
        lesson["id"]: (lesson["startsAt"], lesson["status"]) for lesson in before["lessons"]
    } == {lesson["id"]: (lesson["startsAt"], lesson["status"]) for lesson in after["lessons"]}
    assert len(after["lessons"]) == 15


def test_renewing_a_finished_package_starts_the_lessons_running_again(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """A package capped at `used == size` by #9's sweep has room again, and only
    starts consuming once the new lessons fall due in their own turn."""
    student_id = _create_student(client, admin_headers, "All Used Up", 5, size=5)
    _finish_the_package(client, admin_headers, student_id)
    before = _detail(client, admin_headers, student_id)

    renewed = _renew(client, admin_headers, student_id, 5)
    after = _detail(client, admin_headers, student_id)

    assert renewed.status_code == 200
    assert before["student"]["pkg"]["used"] == before["student"]["pkg"]["size"] == 5
    assert after["student"]["pkg"]["size"] == 10
    assert after["student"]["pkg"]["used"] == 5
    assert [lesson["status"] for lesson in after["lessons"]] == ["done"] * 5 + ["scheduled"] * 5


def test_renewing_a_paused_students_package_keeps_the_lessons_out_of_the_break(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student_id = _create_student(client, admin_headers, "On A Break", 1, size=5)
    paused = client.post(
        f"/admin/students/{student_id}/pause", json={"weeks": 3}, headers=admin_headers
    )
    ends_on = datetime.fromisoformat(paused.json()["data"]["pausedUntil"]).date()

    renewed = _renew(client, admin_headers, student_id, 5)
    after = _detail(client, admin_headers, student_id)

    assert paused.status_code == 200
    assert renewed.status_code == 200
    assert after["student"]["status"] == "paused"
    assert after["student"]["pkg"]["size"] == 10
    assert all(time.date() >= ends_on for time in _times(after["lessons"])[5:])


def test_renewing_a_paused_student_with_nothing_scheduled_waits_for_the_break(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The case where the pause date is the only thing holding the lessons back.

    With lessons still scheduled, #12's forward shift has already pushed them
    past `ends_on` and the anchor follows them. With none left to follow, the
    pause row itself is what decides -- not an approximation of it.
    """
    student_id = _create_student(client, admin_headers, "Break First", 2, size=None)
    paused = client.post(
        f"/admin/students/{student_id}/pause", json={"weeks": 4}, headers=admin_headers
    )
    ends_on = datetime.fromisoformat(paused.json()["data"]["pausedUntil"]).date()

    renewed = _renew(client, admin_headers, student_id, 5)
    after = _detail(client, admin_headers, student_id)
    times = _times(after["lessons"])

    assert renewed.status_code == 200
    assert len(times) == 5
    assert all(time.date() >= ends_on for time in times)
    # The first one is the earliest Tuesday the break leaves open, not later.
    assert times[0].date() - timedelta(weeks=1) < ends_on
    assert all(time.weekday() == 1 for time in times)


def test_renewing_a_flagged_students_package_succeeds_and_leaves_the_flag(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Flagging stops the student booking and moving, not the teacher selling."""
    student_id = _create_student(client, admin_headers, "Under Question", 3, size=5)
    flagged = client.post(
        f"/admin/students/{student_id}/status", json={"status": "flagged"}, headers=admin_headers
    )

    renewed = _renew(client, admin_headers, student_id, 8)
    after = _detail(client, admin_headers, student_id)

    assert flagged.status_code == 200
    assert renewed.status_code == 200
    assert after["student"]["status"] == "flagged"
    assert after["student"]["pkg"]["size"] == 13
    assert len(after["lessons"]) == 13


def test_a_size_that_is_not_on_the_price_list_is_refused(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The stored total is unconstrained; what can be bought in one go is not."""
    student_id = _create_student(client, admin_headers, "Odd Sizes", 4, size=5)

    seven = _renew(client, admin_headers, student_id, 7)
    hundred = _renew(client, admin_headers, student_id, 100)
    zero = _renew(client, admin_headers, student_id, 0)
    opened_seven = client.post(
        f"/admin/students/{student_id}/package", json={"size": 7}, headers=admin_headers
    )
    after = _detail(client, admin_headers, student_id)

    assert seven.status_code == 422
    assert hundred.status_code == 422
    assert zero.status_code == 422
    # The same answer the sibling endpoint gives, from the same request model.
    assert opened_seven.status_code == 422
    assert after["student"]["pkg"]["size"] == 5
    assert len(after["lessons"]) == 5


def test_a_generated_time_that_is_already_booked_is_refused(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The same 409 opening a package gives, and nothing is half-applied."""
    holder = _create_student(client, admin_headers, "Holds The Slot", 5, "14:00", size=10)
    # No lessons of their own, so the renewal falls back to the fresh-package
    # anchor -- next week's Friday 14:00, which the student above is sitting on.
    newcomer = _create_student(client, admin_headers, "Wants The Slot", 5, "14:00", size=None)

    renewed = _renew(client, admin_headers, newcomer, 5)
    after = _detail(client, admin_headers, newcomer)

    assert renewed.status_code == 409
    assert renewed.json()["error"]["code"] == "SLOT_TAKEN"
    assert after["student"]["pkg"]["size"] == 10
    assert after["lessons"] == []
    assert len(_detail(client, admin_headers, holder)["lessons"]) == 10


def test_marking_an_invoice_sent_no_longer_opens_the_next_package(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """It flags the invoice. Selling more lessons is now a separate decision."""
    student_id = _create_student(client, admin_headers, "Invoice Only", 1, size=5)
    _finish_the_package(client, admin_headers, student_id)
    before = _detail(client, admin_headers, student_id)
    rows_before = _package_rows(student_id)

    invoiced = client.post(
        f"/admin/packages/{before['student']['pkg']['id']}/invoiced", headers=admin_headers
    )
    after = _detail(client, admin_headers, student_id)

    assert invoiced.status_code == 200
    assert _package_rows(student_id) == rows_before
    assert after["student"]["pkg"]["periodNo"] == before["student"]["pkg"]["periodNo"]
    assert after["student"]["pkg"]["size"] == before["student"]["pkg"]["size"]
    assert after["student"]["invoiceSent"] is True
    assert after["lessons"] == before["lessons"]


def test_a_renewed_package_drops_off_the_invoice_alerts(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student_id = _create_student(client, admin_headers, "Alerting", 2, size=5)
    lessons = _detail(client, admin_headers, student_id)["lessons"]
    with clock.pinned(max(_times(lessons)) + timedelta(hours=1)):
        alerted = client.get("/admin/alerts", headers=admin_headers).json()["alerts"]

    renewed = _renew(client, admin_headers, student_id, 10)
    remaining = client.get("/admin/alerts", headers=admin_headers).json()["alerts"]
    after = _detail(client, admin_headers, student_id)

    assert renewed.status_code == 200
    assert any(
        alert["type"] == "invoice" and alert["student"]["id"] == student_id for alert in alerted
    )
    assert not any(
        alert["type"] == "invoice" and alert["student"]["id"] == student_id for alert in remaining
    )
    assert after["student"]["invoiceSent"] is False


def test_renewing_after_the_invoice_went_out_clears_the_invoice_flag(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The package is not finished any more, so the invoice no longer covers it."""
    student_id = _create_student(client, admin_headers, "Invoiced Then Renewed", 3, size=5)
    _finish_the_package(client, admin_headers, student_id)
    package_id = _detail(client, admin_headers, student_id)["student"]["pkg"]["id"]
    client.post(f"/admin/packages/{package_id}/invoiced", headers=admin_headers)
    invoiced = _detail(client, admin_headers, student_id)["student"]["invoiceSent"]

    renewed = _renew(client, admin_headers, student_id, 5)
    after = _detail(client, admin_headers, student_id)

    assert invoiced is True
    assert renewed.status_code == 200
    assert after["student"]["invoiceSent"] is False
    assert after["student"]["pkg"]["id"] == package_id
