import datetime as dt

import pandas as pd

from edgefinder.data import nba_snapshot_plan as plan

UTC = dt.timezone.utc


def event(event_id: str, tip_utc: str) -> dict:
    return {"event_id": event_id, "commence_time": tip_utc,
            "home": f"{event_id} home", "away": f"{event_id} away"}


# Eight games on the Nov 4 (Eastern) slate plus one on Nov 5. Tips are
# 7:00pm-10:30pm ET, i.e. 00:00Z-03:30Z on Nov 5.
SLATE = [event(f"g{i}", f"2026-11-05T0{i // 2}:{'00' if i % 2 == 0 else '30'}:00Z")
         for i in range(8)]
TOMORROW = event("tomorrow", "2026-11-06T00:30:00Z")
EVENTS = SLATE + [TOMORROW]

NOON_ET = dt.datetime(2026, 11, 4, 17, 0, tzinfo=UTC)    # 12:00 ET


def snaps(*pairs):
    return pd.DataFrame(pairs, columns=["event_id", "phase"])


def planned(tasks):
    return [(task.event["event_id"], task.phase) for task in tasks]


def test_noon_run_takes_the_first_games_by_tipoff_up_to_the_cap():
    tasks = plan.plan_snapshots(EVENTS, snaps(), NOON_ET, max_games=6)
    assert planned(tasks) == [(f"g{i}", "early") for i in range(6)]


def test_games_on_other_dates_are_never_planned():
    tasks = plan.plan_snapshots(EVENTS, snaps(), NOON_ET, max_games=20)
    assert "tomorrow" not in {task.event["event_id"] for task in tasks}


def test_the_cap_counts_games_already_snapshotted_today():
    done = snaps(("g0", "early"), ("g1", "early"), ("g2", "early"), ("g3", "early"))
    tasks = plan.plan_snapshots(EVENTS, done, NOON_ET, max_games=6)
    assert planned(tasks) == [("g4", "early"), ("g5", "early")]


def test_a_game_is_not_snapshotted_early_twice():
    done = snaps(("g0", "early"))
    tasks = plan.plan_snapshots(EVENTS, done, NOON_ET, max_games=1)
    assert tasks == []


def test_late_snapshot_fires_only_inside_the_window_before_tipoff():
    done = snaps(*[(f"g{i}", "early") for i in range(6)])
    # 22:40Z is 80 minutes before the 00:00Z tip of g0; g1 tips at 00:30Z
    now = dt.datetime(2026, 11, 4, 22, 40, tzinfo=UTC)
    tasks = plan.plan_snapshots(EVENTS, done, now, max_games=6)
    assert planned(tasks) == [("g0", "late")]


def test_late_snapshot_is_taken_once():
    done = snaps(*[(f"g{i}", "early") for i in range(6)], ("g0", "late"))
    now = dt.datetime(2026, 11, 4, 22, 40, tzinfo=UTC)
    assert plan.plan_snapshots(EVENTS, done, now, max_games=6) == []


def test_no_late_snapshot_after_tipoff():
    done = snaps(("g0", "early"))
    now = dt.datetime(2026, 11, 5, 0, 5, tzinfo=UTC)  # g0 already started
    tasks = plan.plan_snapshots(EVENTS, done, now, max_games=6)
    assert ("g0", "late") not in planned(tasks)
    assert ("g0", "early") not in planned(tasks)


def test_no_late_snapshot_without_an_early_one():
    now = dt.datetime(2026, 11, 4, 22, 40, tzinfo=UTC)
    tasks = plan.plan_snapshots([SLATE[0]], snaps(), now, max_games=6)
    assert planned(tasks) == []  # too close to tip for an early price either


def test_games_too_close_to_tipoff_are_skipped_for_early():
    now = dt.datetime(2026, 11, 4, 22, 0, tzinfo=UTC)  # 2h before g0, 2.5h before g1
    tasks = plan.plan_snapshots(SLATE[:2], snaps(), now, max_games=6)
    # g0 is under the 150-minute lead; g1 is exactly at it, which is enough
    assert planned(tasks) == [("g1", "early")]


def test_tip_date_is_the_eastern_calendar_date():
    assert plan.tip_date(event("g", "2026-11-05T00:00:00Z")) == "2026-11-04"   # 7pm ET
    assert plan.tip_date(event("g", "2026-11-05T05:00:00Z")) == "2026-11-05"   # midnight ET


def test_the_slate_date_follows_eastern_time_not_utc():
    # 03:30Z on Nov 5 is 10:30pm ET on Nov 4: still tonight's slate
    late_game = event("late", "2026-11-05T03:30:00Z")
    tasks = plan.plan_snapshots([late_game], snaps(), NOON_ET, max_games=6)
    assert planned(tasks) == [("late", "early")]
