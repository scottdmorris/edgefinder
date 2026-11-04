"""Run one NBA player-points snapshot cycle.

Safe to run repeatedly (e.g. every 30 minutes through the afternoon and
evening): the policy in nba_snapshot_plan decides what is due, so
re-running never spends a request twice on the same job. Each early
snapshot also writes the model's view of every line to the paper ledger.

Usage:  python scripts/nba_props_snapshot.py [--dry-run] [--log-file PATH]
  --dry-run   show what would be fetched without spending any requests
  --log-file  also append the log to PATH (scheduled runs have no console)
"""

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import nba_props, nba_snapshot_plan, nba_stats  # noqa: E402
from edgefinder.models import nba_points  # noqa: E402
from edgefinder.tracking import nba_paper  # noqa: E402

log = logging.getLogger("nba_props_snapshot")


def configure_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:  # pythonw (scheduled runs) has no console
        handlers.append(logging.StreamHandler())
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                        datefmt="%Y-%m-%d %H:%M", handlers=handlers or None)


def load_games(today: dt.date) -> pd.DataFrame:
    season = nba_stats.current_season(today)
    return pd.concat(
        [nba_stats.load_season(s, today=today)
         for s in (nba_stats.previous_season(season), season)],
        ignore_index=True,
    )


def record_early_lines(event: dict, lines: list[dict], games: pd.DataFrame, today: dt.date) -> int:
    game_date = nba_snapshot_plan.tip_time(event).astimezone(
        nba_snapshot_plan.EASTERN).date().isoformat()
    projections = nba_points.project_event(
        event, [line["player"] for line in lines], games,
        season=nba_stats.current_season(today), game_date=game_date)
    rows = nba_paper.build_ledger_rows(
        event, lines, projections,
        recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(), game_date=game_date)
    return nba_paper.append_rows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-file", type=Path)
    args = parser.parse_args()
    configure_logging(args.log_file)

    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(nba_snapshot_plan.EASTERN).date()
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

    games = None
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
        recorded = 0
        if task.phase == "early":
            games = load_games(today) if games is None else games
            recorded = record_early_lines(task.event, lines, games, today)
        log.info("%-5s %s @ %s: %d lines archived, %d added to the ledger",
                 task.phase, task.event["away"], task.event["home"], len(lines), recorded)
    log.info("Odds API requests remaining: %s", nba_props.requests_remaining())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # an unattended run has nobody watching a console, so record the crash
        log.exception("Snapshot run crashed")
        sys.exit(1)
