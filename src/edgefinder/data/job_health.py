"""Did the scheduled jobs actually run? A missed snapshot silently loses picks.

Each job writes a small "heartbeat" when it finishes (when it ran, how it went, one line of
detail) to data/job_heartbeat.json. The app reads them and says so plainly when the
snapshots look stopped or the last run failed, instead of quietly showing yesterday's lines.

Times are stored in UTC and judged in Eastern time, the NBA's clock.
"""

import datetime as dt
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from . import safe_write

log = logging.getLogger(__name__)

HEARTBEAT_PATH = Path(__file__).resolve().parents[3] / "data" / "job_heartbeat.json"
EASTERN = ZoneInfo("America/New_York")

SNAPSHOT_EVERY = dt.timedelta(minutes=30)
BEHIND_AFTER = dt.timedelta(minutes=75)         # two missed runs
STOPPED_AFTER = dt.timedelta(hours=3)
# the snapshot task runs 12:00-22:30; judge it only when a run is expected, with slack
SNAPSHOT_WINDOW = (dt.time(12, 45), dt.time(22, 45))
SETTLE_AT = dt.time(9, 0)
SETTLE_GRACE = dt.timedelta(minutes=45)

OK, NOTHING_DUE, FAILED = "ok", "nothing_due", "failed"


@dataclass(frozen=True)
class Health:
    level: str          # "ok", "warn" or "bad"
    text: str


def record(job: str, outcome: str, detail: str = "", path: Path | None = None,
           now: dt.datetime | None = None) -> None:
    """Write this job's heartbeat. Never raises: a job must not fail over its own bookkeeping."""
    path = path or HEARTBEAT_PATH
    try:
        beats = load(path)
        beats[job] = {"ran_at": (now or dt.datetime.now(dt.timezone.utc)).isoformat(),
                      "outcome": outcome, "detail": detail}
        safe_write.write_text(path, json.dumps(beats, indent=2))
    except Exception:       # noqa: BLE001 - see docstring
        log.exception("could not write the %s heartbeat", job)


def load(path: Path | None = None) -> dict[str, dict]:
    """Every job's last heartbeat; empty if none were written or the file is unreadable."""
    path = path or HEARTBEAT_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _when(beat: dict) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(beat["ran_at"]).astimezone(EASTERN)
    except (KeyError, ValueError, TypeError):
        return None


def _clock(moment: dt.datetime) -> str:
    return moment.strftime("%b %d, %I:%M %p").replace(" 0", " ").lstrip("0") + " ET"


def snapshot_health(beats: dict[str, dict], now: dt.datetime) -> Health:
    """Is the line-recording job running as it should?"""
    beat = beats.get("snapshot")
    when = _when(beat) if beat else None
    if when is None:
        return Health("warn", "No snapshot has reported in yet.")
    now = now.astimezone(EASTERN)
    if beat.get("outcome") == FAILED:
        return Health("bad", f"The last line snapshot failed ({_clock(when)}): "
                             f"{beat.get('detail') or 'no detail'}")
    expected = SNAPSHOT_WINDOW[0] <= now.time() <= SNAPSHOT_WINDOW[1]
    age = now - when
    if expected and age > STOPPED_AFTER:
        return Health("bad", f"Line snapshots look stopped: the last run was {_clock(when)}. "
                             "Picks are not being recorded.")
    if expected and age > BEHIND_AFTER:
        return Health("warn", f"Line snapshots are running behind: last run {_clock(when)}.")
    return Health("ok", f"Lines last checked {_clock(when)}")


def settle_health(beats: dict[str, dict], now: dt.datetime) -> Health:
    """Has last night's grading run? It is due at 9:00 each morning."""
    beat = beats.get("settle")
    when = _when(beat) if beat else None
    now = now.astimezone(EASTERN)
    due = dt.datetime.combine(now.date(), SETTLE_AT, tzinfo=EASTERN)
    if now.time() < SETTLE_AT:
        due -= dt.timedelta(days=1)
    if when is None:
        return Health("warn", "Grading has not run yet.")
    if beat.get("outcome") == FAILED:
        return Health("bad", f"The last grading run failed ({_clock(when)}): "
                             f"{beat.get('detail') or 'no detail'}")
    if now > due + SETTLE_GRACE and when < due:
        return Health("warn", f"Grading is overdue: it last ran {_clock(when)}.")
    return Health("ok", f"Graded {_clock(when)}")


def worst(*healths: Health) -> Health | None:
    """The most serious problem, or None when everything is fine."""
    for level in ("bad", "warn"):
        for health in healths:
            if health.level == level:
                return health
    return None
