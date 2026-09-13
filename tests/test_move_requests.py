"""Declining a move request, and what happens to one nobody ever answers.

A move request used to have exactly one ending: approve, which deleted the row.
Declining now gives it a second (#10), and it keeps the row -- the student is
told the answer, with a reason when the teacher gave one, instead of watching
the request disappear. A request time has overtaken reaches the same kind of
visible ending on its own, as `expired`.

The trap that shape invites is what most of this file is about. While resolving
deleted the row, "a move request row exists for this lesson" and "this lesson is
blocked" were the same sentence, and that reading is spread across the store:
the open-slots query, the pending check, the alerts feed, the pause gate and the
student view's `canMove`. Now that a resolved row survives, every one of those
would read a single decline as a permanent block -- the student could never ask
again and the slot would never come back.
`test_a_declined_request_blocks_neither_its_slot_nor_a_fresh_request` is the one
that would catch that, and it goes through the ordinary student reschedule
endpoint rather than the store, because the endpoint is where a student would
hit it.

Time is pinned with `clock.pinned(...)` from `backend.store` -- the same seam
lesson completion uses -- because a request's requested time is days away and
cannot be waited for.
"""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

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
    return {"id": student_id, "token": created.json()["data"]["token"]}


def _open_slots(client: TestClient, token: str, lesson_id: int) -> list[str]:
    today = datetime.now(STUDIO_TZ).date()
    response = client.get(
        f"/s/{token}/slots",
        params={
            "from": today.isoformat(),
            "to": (today + timedelta(days=21)).isoformat(),
            "lessonId": lesson_id,
        },
    )
    assert response.status_code == 200
    return [slot["startsAt"] for slot in response.json()["slots"]]


def _movable_lesson(client: TestClient, token: str) -> dict:
    """The last upcoming lesson, so a requested slot can fall well before it.

    Taking the last one matters for the expiry tests: they pin the clock past
    the requested time, and a lesson that sat earlier than that would be swept
    to `done` in the same read, mixing two reasons for expiring into one test.
    """
    lessons = [item for item in client.get(f"/s/{token}").json()["lessons"] if item["canMove"]]
    assert lessons
    return lessons[-1]


def _request_a_move(client: TestClient, token: str, lesson: dict) -> tuple[dict, str]:
    """Submit a move request through the student's own endpoint. Returns it and
    the time it asked for."""
    slots = _open_slots(client, token, lesson["id"])
    assert slots
    wanted = slots[0]
    response = client.post(
        f"/s/{token}/lessons/{lesson['id']}/reschedule", json={"startsAt": wanted}
    )
    assert response.status_code == 200, response.json()
    return response.json()["data"], wanted


def _first_movable_lesson(client: TestClient, token: str) -> dict:
    """The soonest lesson that can still be moved, for the opposite setup.

    `_movable_lesson` picks the last one so a requested slot falls before it.
    One test needs the reverse -- a lesson that falls due while the time it
    asked for is still ahead -- and the only lesson with open slots after it is
    an early one, since slots stop at 21 days.
    """
    lessons = [item for item in client.get(f"/s/{token}").json()["lessons"] if item["canMove"]]
    assert lessons
    return lessons[0]


def _request_a_move_to_a_later_slot(
    client: TestClient, token: str, lesson: dict
) -> tuple[dict, str]:
    slots = [
        slot
        for slot in _open_slots(client, token, lesson["id"])
        if datetime.fromisoformat(slot) > datetime.fromisoformat(lesson["startsAt"])
    ]
    assert slots
    response = client.post(
        f"/s/{token}/lessons/{lesson['id']}/reschedule", json={"startsAt": slots[0]}
    )
    assert response.status_code == 200, response.json()
    return response.json()["data"], slots[0]


def _lesson_in_view(client: TestClient, token: str, lesson_id: int) -> dict | None:
    view = client.get(f"/s/{token}").json()
    return next((item for item in view["lessons"] if item["id"] == lesson_id), None)


def _move_alerts(client: TestClient, admin_headers: dict[str, str]) -> list[dict]:
    alerts = client.get("/admin/alerts", headers=admin_headers).json()["alerts"]
    return [item for item in alerts if item["type"] == "moveRequest"]


def test_teacher_declines_a_move_request_and_the_student_is_told_why(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Declined Reason", 3, "14:00")
    lesson = _movable_lesson(client, student["token"])
    request, _ = _request_a_move(client, student["token"], lesson)

    declined = client.post(
        f"/admin/move-requests/{request['id']}/decline",
        json={"reason": "I teach a masterclass that afternoon."},
        headers=admin_headers,
    )

    assert declined.status_code == 200
    assert declined.json()["data"]["status"] == "declined"
    assert declined.json()["data"]["declineReason"] == "I teach a masterclass that afternoon."
    assert declined.json()["data"]["resolvedAt"] is not None
    assert _move_alerts(client, admin_headers) == []
    shown = _lesson_in_view(client, student["token"], lesson["id"])
    assert shown is not None
    assert shown["moveRequestStatus"] == "declined"
    assert shown["declineReason"] == "I teach a masterclass that afternoon."
    assert shown["requestedStartsAt"] is None
    assert shown["startsAt"] == lesson["startsAt"]
    assert shown["canMove"] is True


def test_a_decline_with_no_reason_is_still_a_visible_decline(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """No body, an empty body and a blank reason all mean the same thing."""
    student = _create_student(client, admin_headers, "No Reason", 3, "14:45")
    lesson = _movable_lesson(client, student["token"])
    request, _ = _request_a_move(client, student["token"], lesson)

    declined = client.post(
        f"/admin/move-requests/{request['id']}/decline",
        json={"reason": "   "},
        headers=admin_headers,
    )

    assert declined.status_code == 200
    assert declined.json()["data"]["status"] == "declined"
    assert declined.json()["data"]["declineReason"] is None
    shown = _lesson_in_view(client, student["token"], lesson["id"])
    assert shown is not None
    assert shown["moveRequestStatus"] == "declined"
    assert shown["declineReason"] is None
    assert shown["canMove"] is True


def test_a_decline_needs_no_body_at_all(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "No Body", 3, "15:30")
    lesson = _movable_lesson(client, student["token"])
    request, _ = _request_a_move(client, student["token"], lesson)

    declined = client.post(
        f"/admin/move-requests/{request['id']}/decline", headers=admin_headers
    )

    assert declined.status_code == 200
    assert declined.json()["data"]["status"] == "declined"
    assert declined.json()["data"]["declineReason"] is None


def test_a_declined_request_blocks_neither_its_slot_nor_a_fresh_request(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The whole point of the change, asserted through the student's own path.

    A declined row keeps its `lesson_id` and its `requested_starts_at` forever.
    If the unique indexes stayed unconditional, or if any of the queries that
    used to read "a row exists" as "blocked" kept doing so, this student would
    be stuck for good: the slot would never be offered again and every later
    request for this lesson would come back MOVE_ALREADY_REQUESTED.
    """
    student = _create_student(client, admin_headers, "Asks Again", 3, "16:15")
    lesson = _movable_lesson(client, student["token"])
    request, wanted = _request_a_move(client, student["token"], lesson)
    assert wanted not in _open_slots(client, student["token"], lesson["id"])

    declined = client.post(
        f"/admin/move-requests/{request['id']}/decline", headers=admin_headers
    )
    slots_after = _open_slots(client, student["token"], lesson["id"])
    again = client.post(
        f"/s/{student['token']}/lessons/{lesson['id']}/reschedule", json={"startsAt": wanted}
    )

    assert declined.status_code == 200
    # The time the declined request had reserved is on offer again...
    assert wanted in slots_after
    # ...and the student can ask for that very time a second time.
    assert again.status_code == 200, again.json()
    assert again.json()["data"]["status"] == "pending"
    assert again.json()["data"]["requestedStartsAt"] == wanted
    assert again.json()["data"]["id"] != request["id"]
    shown = _lesson_in_view(client, student["token"], lesson["id"])
    assert shown is not None
    assert shown["requestedStartsAt"] == wanted
    assert shown["moveRequestStatus"] is None
    assert shown["canMove"] is False
    assert len(_move_alerts(client, admin_headers)) == 1


def test_declining_an_already_declined_request_says_so(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Not a silent second success, and not the flat 404 approve used to give."""
    student = _create_student(client, admin_headers, "Twice Declined", 4, "17:00")
    lesson = _movable_lesson(client, student["token"])
    request, _ = _request_a_move(client, student["token"], lesson)
    first = client.post(
        f"/admin/move-requests/{request['id']}/decline",
        json={"reason": "The first answer."},
        headers=admin_headers,
    )

    second = client.post(
        f"/admin/move-requests/{request['id']}/decline",
        json={"reason": "A different answer."},
        headers=admin_headers,
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "MOVE_REQUEST_ALREADY_DECLINED"
    # Nothing was re-stamped and nothing was overwritten.
    shown = _lesson_in_view(client, student["token"], lesson["id"])
    assert shown is not None
    assert shown["declineReason"] == "The first answer."
    assert store.move_request_for_lesson(lesson["id"]).resolved_at == datetime.fromisoformat(
        first.json()["data"]["resolvedAt"]
    )


def test_approving_a_declined_request_says_it_was_already_declined(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Approve After Decline", 4, "17:45")
    lesson = _movable_lesson(client, student["token"])
    request, _ = _request_a_move(client, student["token"], lesson)
    client.post(f"/admin/move-requests/{request['id']}/decline", headers=admin_headers)

    approved = client.post(
        f"/admin/move-requests/{request['id']}/approve", headers=admin_headers
    )

    assert approved.status_code == 409
    assert approved.json()["error"]["code"] == "MOVE_REQUEST_ALREADY_DECLINED"
    shown = _lesson_in_view(client, student["token"], lesson["id"])
    assert shown is not None
    assert shown["startsAt"] == lesson["startsAt"]


def test_declining_a_request_that_does_not_exist_is_not_found(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post("/admin/move-requests/9999/decline", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_reason_longer_than_the_column_is_refused(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """500 characters, the same limit a blackout note carries."""
    student = _create_student(client, admin_headers, "Long Reason", 4, "14:00")
    lesson = _movable_lesson(client, student["token"])
    request, _ = _request_a_move(client, student["token"], lesson)

    too_long = client.post(
        f"/admin/move-requests/{request['id']}/decline",
        json={"reason": "x" * 501},
        headers=admin_headers,
    )
    at_the_limit = client.post(
        f"/admin/move-requests/{request['id']}/decline",
        json={"reason": "x" * 500},
        headers=admin_headers,
    )

    assert too_long.status_code == 422
    assert at_the_limit.status_code == 200
    assert at_the_limit.json()["data"]["declineReason"] == "x" * 500


def test_a_request_whose_time_has_passed_expires_instead_of_being_approved(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Nobody answered, and the time it asked for came and went.

    The old behaviour approved it anyway or, once the slot recheck caught up,
    blamed SLOT_TAKEN -- which pointed at the wrong problem entirely. It now
    ends visibly, as `expired`, and the student is free to ask again.
    """
    student = _create_student(client, admin_headers, "Never Answered", 4, "15:30")
    lesson = _movable_lesson(client, student["token"])
    request, wanted = _request_a_move(client, student["token"], lesson)

    with clock.pinned(datetime.fromisoformat(wanted) + timedelta(minutes=1)):
        alerts_after_the_time_passed = _move_alerts(client, admin_headers)
    approved = client.post(
        f"/admin/move-requests/{request['id']}/approve", headers=admin_headers
    )
    shown = _lesson_in_view(client, student["token"], lesson["id"])
    again = client.post(
        f"/s/{student['token']}/lessons/{lesson['id']}/reschedule", json={"startsAt": wanted}
    )

    assert alerts_after_the_time_passed == []
    assert approved.status_code == 409
    assert approved.json()["error"]["code"] == "MOVE_REQUEST_EXPIRED"
    assert shown is not None
    assert shown["moveRequestStatus"] == "expired"
    assert shown["declineReason"] is None
    assert shown["requestedStartsAt"] is None
    assert shown["startsAt"] == lesson["startsAt"]
    assert shown["canMove"] is True
    assert again.status_code == 200, again.json()
    assert again.json()["data"]["status"] == "pending"


def test_a_request_expires_when_its_lesson_is_swept_done(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The other half of stale: the lesson it wanted to move already happened.

    The requested time here is still in the future. What makes the request
    pointless is that the lesson stopped being scheduled, so there is nothing
    left to move -- and approving it would drag a finished lesson to a new date.

    The student-visible half of this cannot be asserted: a lesson that is `done`
    is not an upcoming lesson, so it is not on the student's page at all and
    cannot be re-requested. That is `LESSON_NOT_MOVABLE`'s job, not this one's.
    """
    student = _create_student(client, admin_headers, "Lesson Already Done", 4, "16:15")
    lesson = _first_movable_lesson(client, student["token"])
    request, wanted = _request_a_move_to_a_later_slot(client, student["token"], lesson)

    pinned_at = datetime.fromisoformat(lesson["startsAt"]) + timedelta(minutes=1)
    # The one thing that makes this request stale is the lesson, not the clock
    # running past the time it asked for: that time is still ahead.
    assert pinned_at < datetime.fromisoformat(wanted)
    with clock.pinned(pinned_at):
        alerts_after_the_lesson_happened = _move_alerts(client, admin_headers)
        approved = client.post(
            f"/admin/move-requests/{request['id']}/approve", headers=admin_headers
        )
        history = client.get(
            f"/admin/students/{student['id']}", headers=admin_headers
        ).json()["lessons"]

    swept = next(item for item in history if item["id"] == lesson["id"])
    assert alerts_after_the_lesson_happened == []
    assert approved.status_code == 409
    assert approved.json()["error"]["code"] == "MOVE_REQUEST_EXPIRED"
    assert swept["status"] == "done"
    assert swept["startsAt"] == lesson["startsAt"]


def test_marking_a_lesson_done_early_expires_its_move_request(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """No clock involved: the teacher said the lesson happened, so it did."""
    student = _create_student(client, admin_headers, "Done Early", 4, "18:30")
    lesson = _movable_lesson(client, student["token"])
    request, _ = _request_a_move(client, student["token"], lesson)

    done = client.post(f"/admin/lessons/{lesson['id']}/done", headers=admin_headers)
    alerts_after = _move_alerts(client, admin_headers)
    approved = client.post(
        f"/admin/move-requests/{request['id']}/approve", headers=admin_headers
    )

    assert done.status_code == 200
    assert alerts_after == []
    assert approved.status_code == 409
    assert approved.json()["error"]["code"] == "MOVE_REQUEST_EXPIRED"


def test_the_expiry_sweep_counts_what_it_swept_and_never_sweeps_twice(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Idempotent the same way `complete_due_lessons` is: by the transition.

    A row that is already `expired` no longer matches "stale *pending*", so a
    second sweep finds nothing -- and a request that was declined is never
    re-evaluated and never quietly relabelled as expired.
    """
    stale = _create_student(client, admin_headers, "Goes Stale", 5, "14:00")
    answered = _create_student(client, admin_headers, "Answered First", 5, "14:45")
    stale_lesson = _movable_lesson(client, stale["token"])
    answered_lesson = _movable_lesson(client, answered["token"])
    _, stale_wanted = _request_a_move(client, stale["token"], stale_lesson)
    answered_request, _ = _request_a_move(client, answered["token"], answered_lesson)
    client.post(
        f"/admin/move-requests/{answered_request['id']}/decline",
        json={"reason": "Answered before it could go stale."},
        headers=admin_headers,
    )

    with clock.pinned(datetime.fromisoformat(stale_wanted) + timedelta(minutes=1)):
        first_sweep = store.expire_stale_move_requests()
        second_sweep = store.expire_stale_move_requests()

    assert first_sweep == 1
    assert second_sweep == 0
    assert store.move_request_for_lesson(stale_lesson["id"]).status == "expired"
    still_declined = store.move_request_for_lesson(answered_lesson["id"])
    assert still_declined.status == "declined"
    assert still_declined.decline_reason == "Answered before it could go stale."


def test_the_week_view_shows_a_resolved_request_as_history(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The popover keeps showing the request, with a status that is not pending.

    Before this change the request simply disappeared from the cell when it was
    resolved, because the row was gone. The frontend reads `status` to decide
    whether to offer Approve and Decline or render the answer read-only.
    """
    student = _create_student(client, admin_headers, "Week View", 5, "15:30")
    lesson = _movable_lesson(client, student["token"])
    request, _ = _request_a_move(client, student["token"], lesson)
    client.post(
        f"/admin/move-requests/{request['id']}/decline",
        json={"reason": "Not that week."},
        headers=admin_headers,
    )

    lesson_date = datetime.fromisoformat(lesson["startsAt"]).astimezone(STUDIO_TZ).date()
    monday = lesson_date - timedelta(days=lesson_date.weekday())
    week = client.get(
        "/admin/api/week", params={"start": monday.isoformat()}, headers=admin_headers
    ).json()

    cell = next(
        cell
        for day in week["days"]
        for cell in day["cells"]
        if cell.get("lessonId") == lesson["id"]
    )
    assert cell["moveRequest"]["status"] == "declined"
    assert cell["moveRequest"]["declineReason"] == "Not that week."


def test_declining_lets_a_blocked_break_be_taken(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """A pending request holds up a pause (#12); an answered one must not.

    Declining is the teacher's way of clearing that gate, which is exactly what
    the goal of this task says it should be.
    """
    student = _create_student(client, admin_headers, "Wants A Break", 5, "16:15")
    lesson = _movable_lesson(client, student["token"])
    request, _ = _request_a_move(client, student["token"], lesson)

    blocked = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
    )
    client.post(f"/admin/move-requests/{request['id']}/decline", headers=admin_headers)
    allowed = client.post(
        f"/admin/students/{student['id']}/pause", json={"weeks": 2}, headers=admin_headers
    )

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "MOVE_REQUEST_PENDING"
    assert allowed.status_code == 200
