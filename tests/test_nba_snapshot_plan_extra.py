"""Boundary and idempotence checks on the snapshot budget policy.

All times are UTC; November 2026 is on EST (UTC-5), so 7:00 pm ET is 00:00Z.
"""

import datetime as dt

import pandas as pd
import pytest

from edgefinder.data import nba_snapshot_plan as plan

UTC = dt.timezone.utc
MIN = dt.timedelta(minutes=1)
EMPTY = pd.DataFrame(columns=["event_id", "phase"])


def at(hour, minute=0, day=5):
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def event(event_id, tip):
    return {"event_id": event_id, "home": "H", "away": "A",
            "commence_time": tip.strftime("%Y-%m-%dT%H:%M:%SZ")}


def done(*pairs):
    return pd.DataFrame(list(pairs), columns=["event_id", "phase"])


def phases(tasks):
    return [(t.event["event_id"], t.phase) for t in tasks]


# ---- dates ------------------------------------------------------------------------------------------

def test_tip_date_is_the_eastern_calendar_date():
    assert plan.tip_date({"commence_time": "2026-11-05T01:30:00Z"}) == "2026-11-04"   # 8:30 pm ET
    assert plan.tip_date({"commence_time": "2026-11-05T05:00:00Z"}) == "2026-11-05"   # midnight ET
    assert plan.tip_date({"commence_time": "2026-11-05T04:59:00Z"}) == "2026-11-04"


def test_tip_time_parses_the_z_suffix_as_utc():
    assert plan.tip_time({"commence_time": "2026-11-05T00:00:00Z"}) == at(0)


def test_the_tonight_slate_is_the_eastern_date_of_now_not_the_utc_date():
    # now = 03:00Z Nov 5 = 10:00 pm ET Nov 4, so a 01:00Z tip (8 pm ET Nov 4) is tonight
    # and a 23:00Z Nov 5 tip (6 pm ET Nov 5) is tomorrow night.
    tonight = event("tonight", dt.datetime(2026, 11, 5, 1, tzinfo=UTC))
    tomorrow = event("tomorrow", dt.datetime(2026, 11, 5, 23, tzinfo=UTC))
    tasks = plan.plan_snapshots([tonight, tomorrow], EMPTY, dt.datetime(2026, 11, 4, 22, 30, tzinfo=UTC))
    assert phases(tasks) == [("tonight", "early")]


# ---- early window boundaries -----------------------------------------------------------------------------

@pytest.mark.parametrize("minutes_to_tip, expected", [
    (241, False), (240, True), (200, True), (151, True), (150, True), (149, False), (0, False),
])
def test_early_window_is_150_to_240_minutes_inclusive(minutes_to_tip, expected):
    now = at(20)
    tip = now + minutes_to_tip * MIN
    tasks = plan.plan_snapshots([event("e", tip)], EMPTY, now)
    assert (phases(tasks) == [("e", "early")]) is expected


def test_custom_windows_are_honoured():
    now = at(20)
    tip = now + 60 * MIN
    tasks = plan.plan_snapshots([event("e", tip)], EMPTY, now,
                                min_early_lead=30 * MIN, max_early_lead=90 * MIN)
    assert phases(tasks) == [("e", "early")]


# ---- late window boundaries ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("minutes_to_tip, expected", [
    (91, False), (90, True), (45, True), (1, True), (0, False), (-5, False),
])
def test_late_snapshot_is_inside_90_minutes_before_tip_and_never_after(minutes_to_tip, expected):
    now = at(23)
    tip = now + minutes_to_tip * MIN
    tasks = plan.plan_snapshots([event("e", tip)], done(("e", "early")), now)
    assert (phases(tasks) == [("e", "late")]) is expected


def test_no_late_snapshot_without_an_early_one():
    now = at(23)
    assert plan.plan_snapshots([event("e", now + 30 * MIN)], EMPTY, now) == []


# ---- the budget --------------------------------------------------------------------------------------------------------------

def many(count, now):
    # all tip 3 hours out, a minute apart, so they are all inside the early window
    return [event(f"e{i}", now + 180 * MIN + i * MIN) for i in range(count)]


def test_at_most_six_games_get_an_early_snapshot_earliest_tip_first():
    now = at(20)
    tasks = plan.plan_snapshots(list(reversed(many(9, now))), EMPTY, now)
    assert phases(tasks) == [(f"e{i}", "early") for i in range(6)]


def test_games_already_snapshotted_use_up_the_budget():
    now = at(20)
    already = done(("e0", "early"), ("e1", "early"), ("e2", "early"), ("e3", "early"))
    tasks = plan.plan_snapshots(many(9, now), already, now)
    assert phases(tasks) == [("e4", "early"), ("e5", "early")]


def test_a_full_budget_still_allows_the_late_snapshots():
    now = at(23)
    events = [event(f"e{i}", now + 60 * MIN) for i in range(6)]
    already = done(*[(f"e{i}", "early") for i in range(6)])
    assert phases(plan.plan_snapshots(events, already, now)) == [(f"e{i}", "late") for i in range(6)]


def test_max_games_can_be_changed_and_zero_means_none():
    now = at(20)
    assert len(plan.plan_snapshots(many(9, now), EMPTY, now, max_games=2)) == 2
    assert plan.plan_snapshots(many(9, now), EMPTY, now, max_games=0) == []


def test_games_outside_the_early_window_do_not_use_up_the_budget():
    now = at(20)
    far = [event(f"far{i}", now + 600 * MIN) for i in range(3)]       # 10 hours out
    near = [event("near", now + 180 * MIN)]
    assert phases(plan.plan_snapshots(far + near, EMPTY, now, max_games=1)) == [("near", "early")]


# ---- idempotence ----------------------------------------------------------------------------------------------------------------

def test_replanning_after_recording_the_tasks_gives_no_repeats():
    now = at(20)
    events = many(4, now)
    snapshots = EMPTY
    first = plan.plan_snapshots(events, snapshots, now)
    assert len(first) == 4
    snapshots = done(*phases(first))
    assert plan.plan_snapshots(events, snapshots, now) == []


def test_a_game_is_snapshotted_early_then_late_then_never_again():
    tip = at(0, day=6)
    ev = event("g", tip)
    steps = []
    snapshots = EMPTY
    for now in (tip - 200 * MIN, tip - 190 * MIN, tip - 60 * MIN, tip - 50 * MIN, tip - 10 * MIN):
        tasks = plan.plan_snapshots([ev], snapshots, now)
        steps.append(phases(tasks))
        if tasks:
            snapshots = pd.concat([snapshots, done(*phases(tasks))], ignore_index=True)
    assert steps == [[("g", "early")], [], [("g", "late")], [], []]


def test_no_events_no_tasks():
    assert plan.plan_snapshots([], EMPTY, at(20)) == []


def test_tasks_carry_the_original_event():
    ev = event("e", at(20) + 180 * MIN)
    task = plan.plan_snapshots([ev], EMPTY, at(20))[0]
    assert task.event is ev and task.phase == "early"
