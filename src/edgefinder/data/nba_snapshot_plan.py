"""Which NBA games to snapshot right now, given a tight request budget.

Policy, decided purely from the clock and what was already archived, so
the job can run every half hour and stay idempotent:

- early: the first MAX_GAMES games of tonight's slate (by tip-off) get one
  snapshot, as long as tip-off is still at least MIN_EARLY_LEAD away. This
  is the price a paper pick is made at.
- late: each snapshotted game gets one more inside LATE_WINDOW before
  tip-off, the closest we can afford to a closing line.

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


@dataclass(frozen=True)
class SnapshotTask:
    event: dict
    phase: str  # "early" or "late"


def tip_time(event: dict) -> dt.datetime:
    return dt.datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))


def plan_snapshots(
    events: list[dict],
    snapshots: pd.DataFrame,
    now: dt.datetime,
    max_games: int = DEFAULT_MAX_GAMES,
    late_window: dt.timedelta = LATE_WINDOW,
    min_early_lead: dt.timedelta = MIN_EARLY_LEAD,
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
        elif room > 0 and until_tip >= min_early_lead:
            tasks.append(SnapshotTask(event, "early"))
            room -= 1
    return tasks
