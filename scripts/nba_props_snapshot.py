"""Run one NBA player-points snapshot cycle.

Safe to run repeatedly (e.g. every 30 minutes through the afternoon and
evening): the policy in nba_snapshot_plan decides what is due, so
re-running never spends a request twice on the same job. Each early
snapshot also writes every registered model's view of every line to the
paper ledger, so the models are judged head to head on the same lines.

Usage:  python scripts/nba_props_snapshot.py [--dry-run] [--backfill-models] [--log-file PATH]
  --dry-run          show what would be fetched or recorded; spends and writes nothing
  --backfill-models  price already-archived early snapshots with any model that hasn't
                     yet, for games that haven't tipped off. Spends no API requests.
  --log-file         also append the log to PATH (scheduled runs have no console)
"""

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import nba_props, nba_snapshot_plan, nba_stats  # noqa: E402
from edgefinder.models import nba_minutes_points, nba_points  # noqa: E402
from edgefinder.tracking import nba_recording  # noqa: E402

log = logging.getLogger("nba_props_snapshot")

# three seasons to train the minutes model, plus one more for its priors
HISTORY_SEASONS = 4


def configure_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:  # pythonw (scheduled runs) has no console
        handlers.append(logging.StreamHandler())
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                        datefmt="%Y-%m-%d %H:%M", handlers=handlers or None)


def build_models(today: dt.date) -> list[nba_recording.RegisteredModel]:
    """Every model that prices tonight's lines. The first is the original
    rolling-average model, built exactly as before (two seasons of history)."""
    season = nba_stats.current_season(today)
    games = pd.concat(
        [nba_stats.load_season(s, today=today)
         for s in nba_stats.recent_seasons(today, HISTORY_SEASONS)],
        ignore_index=True)
    recent = games[games["season"].isin(nba_stats.recent_seasons(today, 2))]

    def rolling_average(event: dict, names: list[str]) -> dict[str, dict]:
        return nba_points.project_event(
            event, names, recent, season=season, game_date=nba_snapshot_plan.tip_date(event))

    return [
        nba_recording.RegisteredModel(
            nba_points.MODEL_VERSION, nba_points.MODEL_DISPERSION, rolling_average),
        nba_recording.RegisteredModel(
            nba_minutes_points.MODEL_VERSION, nba_minutes_points.MODEL_DISPERSION,
            nba_minutes_points.LiveProjector(games, season)),
    ]


class Models:
    """Loads history and builds the models only when first needed, so runs
    with nothing to record stay fast."""

    def __init__(self, today: dt.date):
        self._today = today
        self._models: list[nba_recording.RegisteredModel] | None = None

    def get(self) -> list[nba_recording.RegisteredModel]:
        if self._models is None:
            self._models = build_models(self._today)
        return self._models


def record_lines(event: dict, lines: list[dict], models: Models) -> dict[str, int]:
    return nba_recording.record_event(
        event, lines, models.get(),
        recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        game_date=nba_snapshot_plan.tip_date(event))


def describe(added: dict[str, int]) -> str:
    return ", ".join(f"{version} +{count}" for version, count in added.items())


def backfill_models(models: Models, now: dt.datetime, dry_run: bool) -> None:
    """Price archived early snapshots with models that haven't yet. Only
    games that haven't tipped off: projections use games through last
    night, so pricing a game that already started would be hindsight."""
    for event, lines in nba_props.early_snapshots_by_event(nba_props.load_snapshots()):
        matchup = f"{event['away']} @ {event['home']}"
        if nba_snapshot_plan.tip_time(event) <= now:
            log.info("skip %s: already tipped off", matchup)
        elif dry_run:
            log.info("would price %s (%d lines)", matchup, len(lines))
        else:
            log.info("%s: %s", matchup, describe(record_lines(event, lines, models)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backfill-models", action="store_true")
    parser.add_argument("--log-file", type=Path)
    args = parser.parse_args()
    configure_logging(args.log_file)

    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(nba_snapshot_plan.EASTERN).date()
    models = Models(today)

    if args.backfill_models:
        backfill_models(models, now, args.dry_run)
        return

    try:
        events = nba_props.upcoming_events()
    except nba_props.PropsApiError as exc:
        log.error("Could not list NBA games: %s", exc)
        sys.exit(1)
    tasks = nba_snapshot_plan.plan_snapshots(events, nba_props.load_snapshots(), now)
    if not tasks:
        log.info("Nothing due right now.")
        return
    for task in tasks:
        log.info("due: %-5s %s @ %s", task.phase, task.event["away"], task.event["home"])
    if args.dry_run:
        log.info("(dry run: no requests spent)")
        return

    for task in tasks:
        remaining = nba_props.requests_remaining()
        if remaining is not None and remaining <= nba_props.QUOTA_RESERVE:
            log.info("Stopping: %s requests left, keeping a reserve of %s.",
                     remaining, nba_props.QUOTA_RESERVE)
            break
        try:
            lines = nba_props.fetch_event_lines(task.event)
        except nba_props.PropsApiError as exc:
            log.info("Stopping: %s", exc)
            break
        nba_props.append_snapshot(
            task.event, task.phase, lines, dt.datetime.now(dt.timezone.utc).isoformat())
        recorded = describe(record_lines(task.event, lines, models)) if task.phase == "early" else "-"
        log.info("%-5s %s @ %s: %d lines archived, ledger %s",
                 task.phase, task.event["away"], task.event["home"], len(lines), recorded)
    log.info("Odds API requests remaining: %s", nba_props.requests_remaining())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # an unattended run has nobody watching a console, so record the crash
        log.exception("Snapshot run crashed")
        sys.exit(1)
