"""Where generated lessons actually land (#11).

Opening a package and topping one up both hand a weekly slot and a count to the
same function, and these tests hold it to what that function promises: a lesson
only ever lands on an instant the teacher is available for, that is not blacked
out, and that nothing else is holding; a blocked candidate rolls forward a week
at a time and carries the rest of the series with it; the count always comes out
exact; and when there is nowhere to put a lesson at all, the call fails whole
rather than writing part of a package.

The same cases are run through both call sites on purpose. That is the point of
the issue: one shared placement function, so the top-up path cannot quietly keep
the old blackout-blind behaviour. If a change ever splits the two apart, the
`_top_up` half of these tests is what fails.

No date is written down anywhere. Every instant here is derived from what the
preview endpoint says the package *would* get, which is also what the tests use
to aim a blackout at a particular lesson of a particular series.

The seeded studio's availability is the grid these tests lean on: Tuesday holds
all seven hours and carries only two seeded lessons (16:15 and 18:30), which
makes it the roomy day. Monday's availability starts at 14:45, which makes
Monday 14:00 a real off-grid slot rather than a contrived one.
"""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.store import PLACEMENT_SEARCH_WEEKS, STUDIO_TZ


TUESDAY = 2
MONDAY = 1


def _create_student(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    slot_day: int,
    slot_time: str,
) -> dict:
    """A student with the package they are created with: a row, and no lessons."""
    created = client.post(
        "/admin/students",
        json={"name": name, "slotDay": slot_day, "slotTime": slot_time},
        headers=admin_headers,
    )
    assert created.status_code == 201
    return created.json()["data"]


def _detail(client: TestClient, admin_headers: dict[str, str], student_id: int) -> dict:
    response = client.get(f"/admin/students/{student_id}", headers=admin_headers)
    assert response.status_code == 200
    return response.json()


def _preview(client: TestClient, admin_headers: dict[str, str], student_id: int, size: int):
    return client.get(
        f"/admin/students/{student_id}/package/preview",
        params={"size": size},
        headers=admin_headers,
    )


def _preview_top_up(client: TestClient, admin_headers: dict[str, str], student_id: int, size: int):
    return client.get(
        f"/admin/students/{student_id}/package/renew/preview",
        params={"size": size},
        headers=admin_headers,
    )


def _open(client: TestClient, admin_headers: dict[str, str], student_id: int, size: int):
    return client.post(
        f"/admin/students/{student_id}/package", json={"size": size}, headers=admin_headers
    )


def _top_up(client: TestClient, admin_headers: dict[str, str], student_id: int, size: int):
    return client.post(
        f"/admin/students/{student_id}/package/renew", json={"size": size}, headers=admin_headers
    )


def _instants(values: list[str]) -> list[datetime]:
    return sorted(datetime.fromisoformat(value).astimezone(STUDIO_TZ) for value in values)


def _dates(response) -> list[datetime]:
    """The instants a preview says a call would create."""
    assert response.status_code == 200, response.json()
    return _instants(response.json()["preview"]["dates"])


def _lesson_times(client: TestClient, admin_headers: dict[str, str], student_id: int):
    return _instants(
        [lesson["startsAt"] for lesson in _detail(client, admin_headers, student_id)["lessons"]]
    )


def _weekly(first: datetime, count: int) -> list[datetime]:
    """`count` instants a week apart from `first`, keeping the wall-clock time.

    Recombined from the studio-local date rather than by adding to the instant,
    the same way the store builds a weekly series, so a run that crosses a
    daylight-saving change still lands on the slot it is meant to block.
    """
    local = first.astimezone(STUDIO_TZ)
    return [
        datetime.combine(local.date() + timedelta(weeks=index), local.timetz())
        for index in range(count)
    ]


def _black_out(
    client: TestClient, admin_headers: dict[str, str], instants: list[datetime], note: str
) -> None:
    for instant in instants:
        response = client.post(
            "/admin/blackout",
            json={"startsAt": instant.isoformat(), "note": note},
            headers=admin_headers,
        )
        assert response.status_code == 200


def _error(response) -> str:
    return response.json()["error"]["code"]


# --------------------------------------------------------------- fresh package


def test_a_blackout_on_the_first_lesson_moves_the_whole_package_a_week_out(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The first lesson of a series gets rolled forward like any other one."""
    student = _create_student(client, admin_headers, "First One Blocked", TUESDAY, "14:00")
    planned = _dates(_preview(client, admin_headers, student["id"], 5))
    _black_out(client, admin_headers, planned[:1], "Tuner coming")

    opened = _open(client, admin_headers, student["id"], 5)
    placed = _lesson_times(client, admin_headers, student["id"])

    assert opened.status_code == 200
    assert len(placed) == 5
    # Every lesson a week later than it would have been, the last one included:
    # the skip moved the series, it did not drop a lesson out of it.
    assert placed == [when + timedelta(weeks=1) for when in planned]


def test_a_blackout_mid_series_moves_every_lesson_after_it_and_keeps_the_count(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Lesson three is blacked out: three, four and five move, one and two do not."""
    student = _create_student(client, admin_headers, "Third One Blocked", TUESDAY, "14:45")
    planned = _dates(_preview(client, admin_headers, student["id"], 5))
    _black_out(client, admin_headers, planned[2:3], "Recital")

    opened = _open(client, admin_headers, student["id"], 5)
    placed = _lesson_times(client, admin_headers, student["id"])

    assert opened.status_code == 200
    assert len(placed) == 5
    assert placed[:2] == planned[:2]
    assert placed[2:] == [when + timedelta(weeks=1) for when in planned[2:]]


def test_a_weekly_slot_that_is_not_on_the_availability_grid_is_refused(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Monday's hours start at 14:45, so Monday 14:00 is a slot that does not exist."""
    student = _create_student(client, admin_headers, "Off The Grid", MONDAY, "14:00")

    previewed = _preview(client, admin_headers, student["id"], 5)
    opened = _open(client, admin_headers, student["id"], 5)
    after = _detail(client, admin_headers, student["id"])

    assert opened.status_code == 409
    assert _error(opened) == "WEEKLY_SLOT_NOT_AVAILABLE"
    # The same refusal from the preview, so the admin is told before there is a
    # confirm button to press -- and told which slot, not just that something is
    # wrong with it.
    assert previewed.status_code == 409
    assert _error(previewed) == "WEEKLY_SLOT_NOT_AVAILABLE"
    assert "Monday" in previewed.json()["error"]["message"]
    assert "14:00" in previewed.json()["error"]["message"]
    assert after["lessons"] == []
    assert after["student"]["pkg"]["periodNo"] == student["pkg"]["periodNo"]


def test_a_slot_blocked_past_the_search_bound_is_refused_and_writes_nothing(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """A slot with no opening inside the bound fails whole, naming the lesson."""
    student = _create_student(client, admin_headers, "Nowhere To Go", TUESDAY, "15:30")
    planned = _dates(_preview(client, admin_headers, student["id"], 5))
    # Exactly the window the search covers for lesson one, and no more.
    _black_out(
        client, admin_headers, _weekly(planned[0], PLACEMENT_SEARCH_WEEKS), "Sabbatical"
    )

    previewed = _preview(client, admin_headers, student["id"], 5)
    opened = _open(client, admin_headers, student["id"], 5)
    after = _detail(client, admin_headers, student["id"])

    assert opened.status_code == 409
    assert _error(opened) == "NO_OPEN_SLOT_FOUND"
    assert "Nowhere To Go" in opened.json()["error"]["message"]
    assert "Lesson 1" in opened.json()["error"]["message"]
    assert previewed.status_code == 409
    assert _error(previewed) == "NO_OPEN_SLOT_FOUND"
    # Nothing persisted: no lessons, and no second package row -- which would
    # show up here as a period number one higher than the one they had.
    assert after["lessons"] == []
    assert after["student"]["pkg"]["periodNo"] == student["pkg"]["periodNo"]
    assert after["student"]["pkg"]["size"] == student["pkg"]["size"]


def test_the_bound_firing_on_a_later_lesson_still_writes_nothing_at_all(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The atomicity case: lesson one had somewhere to go, lesson two did not.

    The whole series is worked out before a single row is written, so a failure
    on lesson two of five cannot leave lesson one behind -- there is no partial
    package to find afterwards, and no rollback being relied on to remove one.
    """
    student = _create_student(client, admin_headers, "Stops At Two", TUESDAY, "17:00")
    planned = _dates(_preview(client, admin_headers, student["id"], 5))
    # Free on the first week, blocked for the whole of lesson two's search.
    _black_out(
        client,
        admin_headers,
        _weekly(planned[1], PLACEMENT_SEARCH_WEEKS),
        "Long run of nothing",
    )

    opened = _open(client, admin_headers, student["id"], 5)
    after = _detail(client, admin_headers, student["id"])

    assert opened.status_code == 409
    assert _error(opened) == "NO_OPEN_SLOT_FOUND"
    assert "Lesson 2" in opened.json()["error"]["message"]
    assert after["lessons"] == []
    assert after["student"]["pkg"]["periodNo"] == student["pkg"]["periodNo"]


def test_a_time_a_done_lesson_holds_is_not_generated_over(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """"Taken" is any lesson row, not only a scheduled one.

    `lessons.starts_at` is unique studio-wide, so a lesson already marked done
    still owns its instant. Reading only `scheduled` rows would have generated
    straight over the first of these five and failed the insert.
    """
    holder = _create_student(client, admin_headers, "Holds Five", TUESDAY, "17:45")
    assert _open(client, admin_headers, holder["id"], 5).status_code == 200
    held = _lesson_times(client, admin_headers, holder["id"])
    first = _detail(client, admin_headers, holder["id"])["lessons"][0]
    assert client.post(f"/admin/lessons/{first['id']}/done", headers=admin_headers).status_code == 200

    newcomer = _create_student(client, admin_headers, "Wants The Same", TUESDAY, "17:45")
    opened = _open(client, admin_headers, newcomer["id"], 5)
    placed = _lesson_times(client, admin_headers, newcomer["id"])

    assert opened.status_code == 200
    assert len(placed) == 5
    assert not set(placed) & set(held)
    # Past all five of the holder's, the done one included, and no further.
    assert placed[0] == max(held) + timedelta(weeks=1)


def test_a_time_a_pending_move_request_holds_is_not_generated_over(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """A pending request reserves its time against generation too.

    Same definition of "blocked" the student's own booking grid uses -- which is
    the point: the grid cannot offer a time generation would take, or the other
    way round.
    """
    mover = _create_student(client, admin_headers, "Asking To Move", TUESDAY, "14:45")
    assert _open(client, admin_headers, mover["id"], 5).status_code == 200
    # The *second* lesson, always at least nine days out, so the 48-hour notice
    # rule cannot turn this test into a question about what time of day it runs.
    lesson = _detail(client, admin_headers, mover["id"])["lessons"][1]
    target = _create_student(client, admin_headers, "Holds The Target", TUESDAY, "14:00")
    wanted = _dates(_preview(client, admin_headers, target["id"], 5))[0]
    requested = client.post(
        f"/s/{mover['token']}/lessons/{lesson['id']}/reschedule",
        json={"startsAt": wanted.isoformat()},
    )

    opened = _open(client, admin_headers, target["id"], 5)
    placed = _lesson_times(client, admin_headers, target["id"])

    assert requested.status_code == 200
    assert opened.status_code == 200
    assert len(placed) == 5
    assert wanted not in placed
    assert placed[0] == wanted + timedelta(weeks=1)


# ------------------------------------------------------------------- previews


def test_the_preview_lists_exactly_the_dates_the_confirm_creates(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The preview runs the real placement, blackout skips and all, and writes nothing."""
    student = _create_student(client, admin_headers, "Shown First", TUESDAY, "14:00")
    planned = _dates(_preview(client, admin_headers, student["id"], 5))
    _black_out(client, admin_headers, planned[1:2], "Away")
    previewed = _dates(_preview(client, admin_headers, student["id"], 5))
    during = _detail(client, admin_headers, student["id"])

    opened = _open(client, admin_headers, student["id"], 5)
    placed = _lesson_times(client, admin_headers, student["id"])

    # Looking created nothing: no lessons, and the package they were created
    # with, untouched.
    assert during["lessons"] == []
    assert during["student"]["pkg"]["periodNo"] == student["pkg"]["periodNo"]
    assert opened.status_code == 200
    # And what was shown is what landed, skip included.
    assert previewed != planned
    assert placed == previewed


def test_the_top_up_preview_lists_exactly_the_dates_the_confirm_appends(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Shown Again", TUESDAY, "15:30")
    assert _open(client, admin_headers, student["id"], 5).status_code == 200
    existing = _lesson_times(client, admin_headers, student["id"])
    planned = _dates(_preview_top_up(client, admin_headers, student["id"], 5))
    _black_out(client, admin_headers, planned[0:1], "Away")
    previewed = _dates(_preview_top_up(client, admin_headers, student["id"], 5))

    topped_up = _top_up(client, admin_headers, student["id"], 5)
    placed = _lesson_times(client, admin_headers, student["id"])

    assert topped_up.status_code == 200
    assert previewed != planned
    assert placed == sorted(existing + previewed)
    # Nothing already booked moved to make room for the new run.
    assert placed[:5] == existing


# ------------------------------------------------------------ the top-up path


def test_a_blackout_on_the_first_topped_up_lesson_moves_the_top_up_out(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The first lesson of a *top-up* series rolls forward too.

    The case the issue exists for: before this, opening a package and topping
    one up placed lessons by two different routes, and only one of them would
    have been fixed.
    """
    student = _create_student(client, admin_headers, "Topped Up First", TUESDAY, "14:00")
    assert _open(client, admin_headers, student["id"], 5).status_code == 200
    existing = _lesson_times(client, admin_headers, student["id"])
    planned = _dates(_preview_top_up(client, admin_headers, student["id"], 5))
    _black_out(client, admin_headers, planned[:1], "Tuner coming")

    topped_up = _top_up(client, admin_headers, student["id"], 5)
    placed = _lesson_times(client, admin_headers, student["id"])
    after = _detail(client, admin_headers, student["id"])

    assert topped_up.status_code == 200
    assert after["student"]["pkg"]["size"] == 10
    assert placed[:5] == existing
    assert placed[5:] == [when + timedelta(weeks=1) for when in planned]


def test_a_blackout_mid_top_up_moves_every_lesson_after_it_and_keeps_the_count(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Topped Up Middle", TUESDAY, "14:45")
    assert _open(client, admin_headers, student["id"], 5).status_code == 200
    existing = _lesson_times(client, admin_headers, student["id"])
    planned = _dates(_preview_top_up(client, admin_headers, student["id"], 5))
    _black_out(client, admin_headers, planned[2:3], "Recital")

    topped_up = _top_up(client, admin_headers, student["id"], 5)
    placed = _lesson_times(client, admin_headers, student["id"])

    assert topped_up.status_code == 200
    assert len(placed) == 10
    assert placed[:5] == existing
    assert placed[5:7] == planned[:2]
    assert placed[7:] == [when + timedelta(weeks=1) for when in planned[2:]]


def test_a_top_up_on_an_off_grid_slot_is_refused_and_writes_nothing(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The slot can fall off the grid after the package was sold, so it is checked here too."""
    student = _create_student(client, admin_headers, "Moved Off The Grid", TUESDAY, "17:00")
    assert _open(client, admin_headers, student["id"], 5).status_code == 200
    existing = _lesson_times(client, admin_headers, student["id"])
    moved = client.post(
        f"/admin/students/{student['id']}/slot",
        json={"slotDay": MONDAY, "slotTime": "14:00"},
        headers=admin_headers,
    )

    previewed = _preview_top_up(client, admin_headers, student["id"], 5)
    topped_up = _top_up(client, admin_headers, student["id"], 5)
    after = _detail(client, admin_headers, student["id"])

    assert moved.status_code == 200
    assert topped_up.status_code == 409
    assert _error(topped_up) == "WEEKLY_SLOT_NOT_AVAILABLE"
    assert previewed.status_code == 409
    assert _error(previewed) == "WEEKLY_SLOT_NOT_AVAILABLE"
    # `size` is not bumped by a call that places no lessons.
    assert after["student"]["pkg"]["size"] == 5
    assert _lesson_times(client, admin_headers, student["id"]) == existing


def test_a_top_up_with_no_opening_inside_the_bound_is_refused_and_writes_nothing(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    student = _create_student(client, admin_headers, "Topped Up Nowhere", TUESDAY, "17:45")
    assert _open(client, admin_headers, student["id"], 5).status_code == 200
    existing = _lesson_times(client, admin_headers, student["id"])
    planned = _dates(_preview_top_up(client, admin_headers, student["id"], 5))
    _black_out(
        client, admin_headers, _weekly(planned[0], PLACEMENT_SEARCH_WEEKS), "Sabbatical"
    )

    topped_up = _top_up(client, admin_headers, student["id"], 5)
    after = _detail(client, admin_headers, student["id"])

    assert topped_up.status_code == 409
    assert _error(topped_up) == "NO_OPEN_SLOT_FOUND"
    assert "Topped Up Nowhere" in topped_up.json()["error"]["message"]
    assert "Lesson 6" in topped_up.json()["error"]["message"]
    assert after["student"]["pkg"]["size"] == 5
    assert _lesson_times(client, admin_headers, student["id"]) == existing
