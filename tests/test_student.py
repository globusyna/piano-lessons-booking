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


def test_student_can_reschedule_to_an_open_slot(client: TestClient) -> None:
    view = client.get("/s/anna").json()
    lesson_id = view["nextLesson"]["id"]
    today = datetime.now(STUDIO_TZ).date()
    slots = client.get(
        "/s/anna/slots",
        params={"from": today.isoformat(), "to": (today + timedelta(days=21)).isoformat(), "lessonId": lesson_id},
    ).json()["slots"]

    response = client.post(
        f"/s/anna/lessons/{lesson_id}/reschedule", json={"startsAt": slots[0]["startsAt"]}
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == lesson_id
    assert response.json()["data"]["startsAt"] == slots[0]["startsAt"]


def test_reschedule_rejects_taken_slot_and_cross_student_access(client: TestClient) -> None:
    anna_lesson = client.get("/s/anna").json()["nextLesson"]
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


def test_pause_changes_student_state_and_cannot_repeat(client: TestClient) -> None:
    response = client.post("/s/anna/pause-request")
    repeated = client.post("/s/anna/pause-request")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "paused"
    assert client.get("/s/anna").json()["canRequestPause"] is False
    assert repeated.status_code == 403
    assert repeated.json()["error"]["code"] == "STUDENT_PAUSED"
