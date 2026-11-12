"""Which NBA games to snapshot right now, given a tight request budget.

Policy, decided purely from the clock and what was already archived, so
the job can run every half hour and stay idempotent:

- early: the first MAX_GAMES games of tonight's slate (by tip-off) get one
  snapshot once tip-off is between MIN_EARLY_LEAD and MAX_EARLY_LEAD away.
  This is the price a paper pick is made at. It is taken in the last few
  hours rather than at noon so the injury report has mostly settled: a
  projection made before it is published can't know who is out.
- late: each snapshotted game gets one more inside LATE_WINDOW before
  tip-off, the closest we can afford to a closing line.

- Kalshi only: games past MAX_GAMES cost nothing to record from Kalshi, so each still gets
  Kalshi's prices once in its early window and once in its late window (plan_kalshi_only).

Tonight's slate is the Eastern-time date, since that is how NBA nights work.
"""

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pandas as pd

EASTERN = ZoneInfo("America/New_York")
DEFAULT_MAX_GAMES = 6
LATE_WINDOW = dt.timedelta(minutes=90)
MIN_EARLY_LEAD = dt.timedelta(minutes=150)
MAX_EARLY_LEAD = dt.timedelta(minutes=240)


@dataclass(frozen=True)
class SnapshotTask:
    event: dict
    phase: str  # "early" or "late"


def tip_time(event: dict) -> dt.datetime:
    return dt.datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))


def tip_date(event: dict) -> str:
    """The game's Eastern-time calendar date, e.g. '2026-11-04'."""
    return tip_time(event).astimezone(EASTERN).date().isoformat()


def plan_snapshots(
    events: list[dict],
    snapshots: pd.DataFrame,
    now: dt.datetime,
    max_games: int = DEFAULT_MAX_GAMES,
    late_window: dt.timedelta = LATE_WINDOW,
    min_early_lead: dt.timedelta = MIN_EARLY_LEAD,
    max_early_lead: dt.timedelta = MAX_EARLY_LEAD,
) -> list[SnapshotTask]:
    slate_date = now.astimezone(EASTERN).date()
    tonight = sorted(
        (e for e in events if tip_time(e).astimezone(EASTERN).date() == slate_date),
        key=tip_time,
    )
    done = set(zip(snapshots["event_id"], snapshots["phase"]))
    room = max(0, max_games - sum((e["event_id"], "early") in done for e in tonight))

    tasks = []
    for event in tonight:
        event_id = event["event_id"]
        until_tip = tip_time(event) - now
        if (event_id, "early") in done:
            if (event_id, "late") not in done and dt.timedelta(0) < until_tip <= late_window:
                tasks.append(SnapshotTask(event, "late"))
        elif room > 0 and min_early_lead <= until_tip <= max_early_lead:
            tasks.append(SnapshotTask(event, "early"))
            room -= 1
    return tasks


def plan_kalshi_only(
    events: list[dict],
    snapshots: pd.DataFrame,
    now: dt.datetime,
    priced: set[str],
    closed: set[str],
    max_games: int = DEFAULT_MAX_GAMES,
    late_window: dt.timedelta = LATE_WINDOW,
    min_early_lead: dt.timedelta = MIN_EARLY_LEAD,
    max_early_lead: dt.timedelta = MAX_EARLY_LEAD,
) -> list[SnapshotTask]:
    """Tonight's games the Odds API budget does not reach, due for Kalshi's free prices.

    `priced` holds the event ids that already have Kalshi rows in the ledger, `closed` those
    with a saved Kalshi closing price. Early is taken once, on the first run inside the early
    window that finds the game unpriced; late once, and only for a game that was priced."""
    slate_date = now.astimezone(EASTERN).date()
    tonight = [e for e in events if tip_time(e).astimezone(EASTERN).date() == slate_date]
    done = set(zip(snapshots["event_id"], snapshots["phase"]))
    covered = {e["event_id"] for e in tonight if (e["event_id"], "early") in done}
    covered |= {task.event["event_id"] for task in plan_snapshots(
        events, snapshots, now, max_games, late_window, min_early_lead, max_early_lead)}

    tasks = []
    for event in sorted(tonight, key=tip_time):
        event_id = event["event_id"]
        until_tip = tip_time(event) - now
        if event_id in covered:
            continue
        if event_id not in priced:
            if min_early_lead <= until_tip <= max_early_lead:
                tasks.append(SnapshotTask(event, "early"))
        elif event_id not in closed and dt.timedelta(0) < until_tip <= late_window:
            tasks.append(SnapshotTask(event, "late"))
    return tasks
