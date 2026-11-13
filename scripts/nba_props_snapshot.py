"""Run one NBA player-points snapshot cycle.

Safe to run repeatedly (e.g. every 30 minutes through the afternoon and
evening): the policy in nba_snapshot_plan decides what is due, so
re-running never spends a request twice on the same job. Each early
snapshot also writes every registered model's view of every line to the
paper ledger, so the models are judged head to head on the same lines.
The same games' liquid Kalshi prices (points, rebounds, assists, threes) are
recorded at the same moment, with book="kalshi". Kalshi spends no Odds API
requests and its failure never stops the FanDuel work.
The FanDuel request also returns DraftKings' lines at no extra cost; they are archived
to their own file and compared with FanDuel's in the log. Picks stay FanDuel's.

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
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import (  # noqa: E402
    job_health, nba_injuries, nba_props, nba_snapshot_plan, nba_stats)
from edgefinder.models import (  # noqa: E402
    nba_context_points, nba_context_v2, nba_minutes_points, nba_points, nba_stat_model)
from edgefinder.tracking import (  # noqa: E402
    book_gaps, gap_log, nba_alt, nba_kalshi_ledger, nba_paper, nba_recording, price_gaps)

log = logging.getLogger("nba_props_snapshot")

# an X+ call costs one more request per game, so it is capped to stay in budget
MAX_ALT_GAMES = 4

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


def load_history(today: dt.date) -> pd.DataFrame:
    return pd.concat(
        [nba_stats.load_season(s, today=today)
         for s in nba_stats.recent_seasons(today, HISTORY_SEASONS)],
        ignore_index=True)


def build_models(today: dt.date, games: pd.DataFrame) -> list[nba_recording.RegisteredModel]:
    """Every model that prices tonight's lines. The first is the original
    rolling-average model, built exactly as before (two seasons of history)."""
    season = nba_stats.current_season(today)
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
        nba_recording.RegisteredModel(
            nba_context_points.MODEL_VERSION, nba_context_points.MODEL_DISPERSION,
            nba_context_points.LiveProjector(games, season, injuries=nba_injuries.fetch_injuries)),
        nba_recording.RegisteredModel(
            nba_context_v2.MODEL_VERSION, nba_context_v2.MODEL_DISPERSION,
            nba_context_v2.LiveProjector(games, season, injuries=nba_injuries.fetch_injuries)),
    ]


class Models:
    """Loads history and builds the models only when first needed, so runs
    with nothing to record stay fast."""

    def __init__(self, today: dt.date):
        self._today = today
        self._games: pd.DataFrame | None = None
        self._models: list[nba_recording.RegisteredModel] | None = None

    def games(self) -> pd.DataFrame:
        if self._games is None:
            self._games = load_history(self._today)
        return self._games

    def get(self) -> list[nba_recording.RegisteredModel]:
        if self._models is None:
            self._models = build_models(self._today, self.games())
        return self._models

    def kalshi_models(self) -> list[nba_kalshi_ledger.KalshiModel]:
        """The rolling average prices all four Kalshi stats; the points-only
        challengers price Kalshi points alongside it."""
        season = nba_stats.current_season(self._today)
        recent = self.games()[self.games()["season"].isin(
            nba_stats.recent_seasons(self._today, 2))]

        def rolling_average(event: dict, stat: str, names: list[str]) -> dict[str, dict]:
            return nba_stat_model.project_event(
                nba_stat_model.STATS[stat], event, names, recent, season=season,
                game_date=nba_snapshot_plan.tip_date(event))

        def points_only(model: nba_recording.RegisteredModel):
            return lambda event, stat, names: model.project(event, names)

        models = [nba_kalshi_ledger.KalshiModel(
            nba_points.MODEL_VERSION,
            {key: stat.dispersion for key, stat in nba_stat_model.STATS.items()},
            rolling_average)]
        models += [
            nba_kalshi_ledger.KalshiModel(m.version, {"points": m.dispersion}, points_only(m))
            for m in self.get() if m.version != nba_points.MODEL_VERSION]
        return models


def record_lines(event: dict, lines: list[dict], models: Models) -> dict[str, int]:
    return nba_recording.record_event(
        event, lines, models.get(),
        recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        game_date=nba_snapshot_plan.tip_date(event))


def record_alt_lines(event: dict, models: Models) -> None:
    """Price a game's "X+ points" lines too. It costs one more request, so
    only the first MAX_ALT_GAMES games a night get it, and a failure here
    never disturbs the main snapshot."""
    game_date = nba_snapshot_plan.tip_date(event)
    if nba_alt.games_recorded(nba_alt.load_ledger(), game_date) >= MAX_ALT_GAMES:
        return
    remaining = nba_props.requests_remaining()
    if remaining is not None and remaining <= nba_props.QUOTA_RESERVE:
        return
    try:
        lines = nba_props.fetch_alt_lines(event)
    except nba_props.PropsApiError as exc:
        log.info("X+ lines unavailable for %s @ %s: %s", event["away"], event["home"], exc)
        return
    added = nba_alt.record_event(
        event, lines, models.get(),
        recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(), game_date=game_date)
    log.info("X+ points %s @ %s: %d prices, ledger %s",
             event["away"], event["home"], len(lines), describe(added))


def describe(added: dict[str, int]) -> str:
    return ", ".join(f"{version} +{count}" for version, count in added.items())


def record_kalshi(events: list[dict], models: Models) -> None:
    """Record Kalshi prices for the games taking their early snapshot.

    Kalshi costs no Odds API requests, so it ignores the quota reserve. It
    runs after the FanDuel work, and nothing it raises may fail the run."""
    try:
        rows = nba_kalshi_ledger.fetch_kalshi_rows()   # one call per series
        if not rows:
            return
        added = nba_kalshi_ledger.record_kalshi(
            rows, events, models.kalshi_models(),
            recorded_at=dt.datetime.now(dt.timezone.utc).isoformat())
        log.info("Kalshi ledger %s", describe(added))
    except Exception:
        log.exception("Kalshi snapshot failed; the FanDuel snapshot is unaffected")


def archive_other_books(event: dict, phase: str, books: dict[str, list[dict]],
                        fetched_at: str) -> None:
    """Save the other books' lines from the same request and log how they compare with
    FanDuel's. Nothing it raises may fail the run."""
    try:
        fanduel = books.get(nba_props.BOOKMAKER, [])
        for book in nba_props.OTHER_BOOKS:
            lines = books.get(book, [])
            if not lines:
                log.info("%s: no lines for %s @ %s", book, event["away"], event["home"])
                continue
            nba_props.append_book_snapshot(event, phase, book, lines, fetched_at)
            table = book_gaps.compare(fanduel, lines)
            log.info("%s: %d lines archived, %d players on both, %d worth a look",
                     book, len(lines), len(table), len(book_gaps.worth_a_look(table)))
    except Exception:
        log.exception("Archiving the other books failed; the FanDuel snapshot is unaffected")


RETRY_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 20.0


def with_retries(call, attempts: int = RETRY_ATTEMPTS, wait: float | None = None,
                 sleep=time.sleep):
    """Call `call()`, trying again after a pause when the odds service errors. A blip on their
    side (a 502) should not cost a whole 30-minute cycle, and the last error still surfaces."""
    wait = RETRY_WAIT_SECONDS if wait is None else wait
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except nba_props.PropsApiError as exc:
            if attempt == attempts:
                raise
            log.info("Odds API error (%s); retry %d of %d in %.0fs", exc, attempt, attempts - 1,
                     wait)
            sleep(wait)


def log_price_gaps(events: list[dict], ledger_path=None, alt_path=None, log_path=None) -> int:
    """Log tonight's FanDuel-vs-Kalshi price gaps for games that haven't started, so the flag
    can be graded like the picks. Nothing it raises may fail the run. Returns how many it added."""
    try:
        ledger = nba_paper.load_ledger(ledger_path)
        alt = nba_alt.load_ledger(alt_path)
        now = dt.datetime.now(dt.timezone.utc)
        added = 0
        for game_date in sorted({nba_snapshot_plan.tip_date(e) for e in events}):
            gaps = price_gaps.find_gaps(ledger, alt, game_date)
            added += gap_log.append(gap_log.rows_to_log(gaps, ledger, game_date, now), log_path)
        log.info("Price gaps logged: %d", added)
        return added
    except Exception:
        log.exception("Logging price gaps failed; the snapshot is unaffected")
        return 0


def archive_kalshi_closing(events: list[dict]) -> None:
    """Save Kalshi's prices for games about to tip off, so Kalshi picks can be judged against
    a closing price. Free, and nothing it raises may fail the run."""
    try:
        saved = nba_kalshi_ledger.archive_closing(
            nba_kalshi_ledger.fetch_kalshi_rows(), events,
            dt.datetime.now(dt.timezone.utc).isoformat())
        log.info("Kalshi closing prices saved: %d", saved)
    except Exception:
        log.exception("Kalshi closing snapshot failed; the FanDuel snapshot is unaffected")


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


def plan_kalshi_only(events: list[dict], now: dt.datetime) -> list[nba_snapshot_plan.SnapshotTask]:
    """Games past the Odds API budget that are due for Kalshi's free prices. Planning them
    reads only local files, and a failure here must not stop the FanDuel snapshot."""
    try:
        ledger = nba_paper.load_ledger()
        priced = set(ledger.loc[ledger["book"] == "kalshi", "event_id"])
        closed = set(nba_kalshi_ledger.load_snapshots()["event_id"])
        return nba_snapshot_plan.plan_kalshi_only(
            events, nba_props.load_snapshots(), now, priced, closed)
    except Exception:
        log.exception("Could not plan the Kalshi-only games; the FanDuel snapshot is unaffected")
        return []


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
        events = with_retries(nba_props.upcoming_events)
    except nba_props.PropsApiError as exc:
        log.error("Could not list NBA games: %s", exc)
        job_health.record("snapshot", job_health.FAILED, f"could not list games: {exc}")
        sys.exit(1)
    tasks = nba_snapshot_plan.plan_snapshots(events, nba_props.load_snapshots(), now)
    kalshi_only = plan_kalshi_only(events, now)
    if not tasks and not kalshi_only:
        log.info("Nothing due right now.")
        job_health.record("snapshot", job_health.NOTHING_DUE)
        return
    for task in tasks:
        log.info("due: %-5s %s @ %s", task.phase, task.event["away"], task.event["home"])
    for task in kalshi_only:
        log.info("due: %-5s %s @ %s (Kalshi only: past the Odds API budget)",
                 task.phase, task.event["away"], task.event["home"])
    if args.dry_run:
        log.info("(dry run: no requests spent)")
        return

    archived, stopped, api_failed = 0, "", False
    for task in tasks:
        remaining = nba_props.requests_remaining()
        if remaining is not None and remaining <= nba_props.QUOTA_RESERVE:
            log.info("Stopping: %s requests left, keeping a reserve of %s.",
                     remaining, nba_props.QUOTA_RESERVE)
            stopped = "request reserve reached"
            break
        try:
            books = with_retries(lambda: nba_props.fetch_event_books(task.event))
        except nba_props.PropsApiError as exc:
            log.info("Stopping: %s", exc)
            stopped, api_failed = str(exc)[:120], True
            break
        lines = books.get(nba_props.BOOKMAKER, [])
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
        nba_props.append_snapshot(task.event, task.phase, lines, fetched_at)
        archive_other_books(task.event, task.phase, books, fetched_at)
        recorded = describe(record_lines(task.event, lines, models)) if task.phase == "early" else "-"
        log.info("%-5s %s @ %s: %d lines archived, ledger %s",
                 task.phase, task.event["away"], task.event["home"], len(lines), recorded)
        archived += 1
        if task.phase == "early":
            record_alt_lines(task.event, models)
    log.info("Odds API requests remaining: %s", nba_props.requests_remaining())
    early_events = [task.event for task in tasks if task.phase == "early"]
    kalshi_early = [task.event for task in kalshi_only if task.phase == "early"]
    if early_events or kalshi_early:
        record_kalshi(early_events + kalshi_early, models)
    if early_events:
        log_price_gaps(early_events)
    late_events = [task.event for task in tasks + kalshi_only if task.phase == "late"]
    if late_events:
        archive_kalshi_closing(late_events)
    detail = f"{archived} of {len(tasks)} due snapshots recorded" + (
        f"; stopped: {stopped}" if stopped else "") + (
        f"; {len(kalshi_only)} Kalshi-only" if kalshi_only else "")
    failed = api_failed and archived == 0
    job_health.record("snapshot", job_health.FAILED if failed else job_health.OK, detail)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # an unattended run has nobody watching a console, so record the crash
        log.exception("Snapshot run crashed")
        job_health.record("snapshot", job_health.FAILED, f"{type(exc).__name__}: {exc}"[:200])
        sys.exit(1)
