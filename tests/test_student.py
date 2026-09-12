from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.store import STUDIO_TZ, store


def test_seeded_student_view_and_invalid_token(client: TestClient) -> None:
    response = client.get("/s/anna")
    invalid = client.get("/s/not-a-token")

    assert response.status_code == 200
    body = response.json()
    assert body["student"]["name"] == "Anna Lie"
    assert body["nextLesson"] == body["lessons"][0]
    assert body["lessons"] == sorted(body["lessons"], key=lambda lesson: lesson["startsAt"])
    assert invalid.status_code == 404
    assert invalid.json()["error"]["code"] == "INVALID_TOKEN"


def test_slots_are_open_sorted_and_inside_requested_range(client: TestClient) -> None:
    today = datetime.now(STUDIO_TZ).date()
    response = client.get(
        "/s/anna/slots",
        params={"from": today.isoformat(), "to": (today + timedelta(days=21)).isoformat()},
    )

    assert response.status_code == 200
    slots = [datetime.fromisoformat(item["startsAt"]) for item in response.json()["slots"]]
    assert slots == sorted(slots)
    assert slots
    assert all(today <= slot.astimezone(STUDIO_TZ).date() <= today + timedelta(days=21) for slot in slots)
    scheduled = {lesson.starts_at for lesson in store.lessons.values() if lesson.status.value == "scheduled"}
    assert not scheduled.intersection(slots)


def test_day_locks_only_after_the_local_day_ends() -> None:
    now = datetime.now(STUDIO_TZ)

    assert store.is_day_locked(now) is False
    assert store.is_day_locked(now - timedelta(days=1)) is True


def test_student_can_request_a_move_to_an_open_slot(client: TestClient) -> None:
    view = client.get("/s/anna").json()
    lesson = next(item for item in view["lessons"] if item["canMove"])
    lesson_id = lesson["id"]
    today = datetime.now(STUDIO_TZ).date()
    slots = client.get(
        "/s/anna/slots",
        params={"from": today.isoformat(), "to": (today + timedelta(days=21)).isoformat(), "lessonId": lesson_id},
    ).json()["slots"]

    response = client.post(
        f"/s/anna/lessons/{lesson_id}/reschedule", json={"startsAt": slots[0]["startsAt"]}
    )

    assert response.status_code == 200
    assert response.json()["data"]["lessonId"] == lesson_id
    assert response.json()["data"]["requestedStartsAt"] == slots[0]["startsAt"]
    refreshed = client.get("/s/anna").json()
    requested_lesson = next(lesson for lesson in refreshed["lessons"] if lesson["id"] == lesson_id)
    assert requested_lesson["startsAt"] == lesson["startsAt"]
    assert requested_lesson["requestedStartsAt"] == slots[0]["startsAt"]
    assert requested_lesson["canMove"] is False


def test_move_request_rejects_taken_slot_and_cross_student_access(client: TestClient) -> None:
    anna_lesson = next(
        lesson for lesson in client.get("/s/anna").json()["lessons"] if lesson["canMove"]
    )
    other_lesson = client.get("/s/selma").json()["nextLesson"]

    taken = client.post(
        f"/s/anna/lessons/{anna_lesson['id']}/reschedule",
        json={"startsAt": other_lesson["startsAt"]},
    )
    foreign = client.post(
        f"/s/anna/lessons/{other_lesson['id']}/reschedule",
        json={"startsAt": anna_lesson["startsAt"]},
    )

    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "SLOT_TAKEN"
    assert foreign.status_code == 404


def test_move_request_requires_at_least_48_hours_notice(client: TestClient) -> None:
    lesson = next(
        item for item in client.get("/s/anna").json()["lessons"] if item["canMove"]
    )
    lesson_record = store.lessons[lesson["id"]]
    with store._sessions.begin() as session:
        from backend.db_models import LessonRecord

        record = session.get(LessonRecord, lesson_record.id)
        assert record is not None
        record.starts_at = datetime.now(STUDIO_TZ) + timedelta(hours=47, minutes=59)

    view = client.get("/s/anna").json()
    near_lesson = next(item for item in view["lessons"] if item["id"] == lesson["id"])
    assert near_lesson["canMove"] is False

    today = datetime.now(STUDIO_TZ).date()
    slot = client.get(
        "/s/anna/slots",
        params={"from": today.isoformat(), "to": (today + timedelta(days=21)).isoformat(), "lessonId": lesson["id"]},
    ).json()["slots"][0]
    response = client.post(
        f"/s/anna/lessons/{lesson['id']}/reschedule", json={"startsAt": slot["startsAt"]}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MOVE_NOTICE_REQUIRED"


def test_pause_changes_student_state_and_cannot_repeat(client: TestClient) -> None:
    response = client.post("/s/anna/pause-request")
    repeated = client.post("/s/anna/pause-request")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "paused"
    assert client.get("/s/anna").json()["canRequestPause"] is False
    assert repeated.status_code == 403
    assert repeated.json()["error"]["code"] == "STUDENT_PAUSED"
