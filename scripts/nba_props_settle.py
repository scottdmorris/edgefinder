"""Settle finished NBA prop games and report how the model is doing.

Grades picks at a flat 1 unit, voids lines for players who didn't play,
attaches closing-line movement, then reports:
- the record, units and closing-line value of the picks
- Brier scores of the model vs the market's own devigged probability on
  EVERY settled line (the model only has something to offer if it wins)

Usage:  python scripts/nba_props_settle.py [--log-file PATH] [--publish]
  --log-file  also append the report to PATH (scheduled runs have no console)
  --publish   then refresh the README record and the published fingerprint, and commit
              and push those two files (scripts/publish_record.py)
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import job_health, nba_props, nba_snapshot_plan, nba_stats  # noqa: E402
from edgefinder.tracking import (  # noqa: E402
    book_gaps, gap_log, nba_alt, nba_kalshi_ledger, nba_paper)


def build_report(today: dt.date) -> str:
    ledger = nba_paper.load_ledger()
    if ledger.empty:
        return "The ledger is empty: run scripts/nba_props_snapshot.py first."
    games = nba_stats.load_season(nba_stats.current_season(today), today=today)
    fanduel_close, other_close = nba_props.load_snapshots(), nba_props.load_book_snapshots()
    settled = nba_paper.settle(ledger, games, fanduel_close, today,
                               nba_kalshi_ledger.load_snapshots(), other_close)
    logged = nba_paper.log_settlements(ledger, settled)
    nba_paper.save_ledger(settled)

    lines = [f"Ledger: {len(settled)} lines  {settled['status'].value_counts().to_dict()}"
             f"  ({logged} results added to the pick chain)"]
    waiting = int(((settled["status"] == "pending")
                   & (settled["game_date"].astype(str) < today.isoformat())).sum())
    if waiting:
        lines.append(f"WAITING: {waiting} lines from past days are still pending; the game logs "
                     f"only reach {nba_paper.latest_logged(games) or 'nothing'}.")
    versions = sorted(settled["model_version"].dropna().unique())
    for version in versions:
        lines += ["", *version_block(settled, version)]
    if len(versions) > 1:
        comparison = nba_paper.compare_versions(settled)
        lines.append("")
        if comparison.empty:
            lines.append("Head to head: no settled lines priced by every model yet.")
        else:
            lines += ["Head to head on the lines every model priced (Brier, lower is better):",
                      comparison.round({"brier_model": 4, "brier_market": 4}).to_string()]
    lines += alt_block(games, today)
    lines += gap_block(games, today, (fanduel_close, other_close))
    lines += book_gap_block(games, today, (fanduel_close, other_close))
    return "\n".join(lines)


def alt_block(games, today: dt.date) -> list[str]:
    """Settle the X+ points ledger and report each model's picks."""
    alt = nba_alt.load_ledger()
    if alt.empty:
        return []
    settled = nba_alt.settle(alt, games, today)
    nba_alt.save_ledger(settled)
    lines = ["", f"X+ points ledger: {len(settled)} prices  "
                  f"{settled['status'].value_counts().to_dict()}"]
    for version in sorted(settled["model_version"].dropna().unique()):
        s = nba_alt.summary(settled, version)
        lines.append(f"[{version}] X+ picks: {s['picks']} made, {s['settled']} settled, "
                     f"record {s['record']}, {s['units']:+.2f} units ({s['roi_pct']:+.1f}% ROI)")
    return lines


def fair_close_text(facts: dict) -> str:
    """How the bets did against the fair (no-vig) closing price."""
    if not facts["clv_novig_n"]:
        return "vs fair close: n/a"
    return (f"vs fair close {facts['avg_clv_novig_pct']:+.2f}% on {facts['clv_novig_n']}, "
            f"beat it {facts['beat_fair_close_pct']:.0f}%")


def gap_block(games, today: dt.date, closes=()) -> list[str]:
    """Grade the FanDuel-vs-Kalshi price gaps and report how betting them would have done."""
    log = gap_log.load()
    if log.empty:
        return []
    settled = gap_log.attach_closing(gap_log.settle(log, games, today), *closes)
    gap_log.save(settled)
    s = gap_log.summary(settled)
    lines = ["", f"Price gaps: {s['all']['logged']} logged, {s['all']['graded']} graded"]
    for part in ("all", "exact", "estimated"):
        f = s[part]
        lines.append(f"  {part:9s} record {f['record']}, {f['units']:+.2f} units "
                     f"({f['roi_pct']:+.1f}% return), {fair_close_text(f)}")
    return lines


def book_gap_block(games, today: dt.date, closes=()) -> list[str]:
    """Grade the FanDuel-vs-DraftKings gaps the same way."""
    log = gap_log.load(book_gaps.LOG_PATH)
    if log.empty:
        return []
    settled = gap_log.attach_closing(gap_log.settle(log, games, today), *closes)
    gap_log.save(settled, book_gaps.LOG_PATH)
    s = gap_log.summary(settled, splits=book_gaps.HOW)
    lines = ["", f"DraftKings gaps: {s['all']['logged']} logged, {s['all']['graded']} graded"]
    for part, label in (("all", "all"), ("price", "better price"), ("number", "other number")):
        f = s[part]
        lines.append(f"  {label:12s} record {f['record']}, {f['units']:+.2f} units "
                     f"({f['roi_pct']:+.1f}% return), {fair_close_text(f)}")
    return lines


def version_block(settled, version: str) -> list[str]:
    summary = nba_paper.summary(settled, model_version=version)
    clv, move = summary["avg_clv_pct"], summary["avg_line_move"]
    lines = [
        f"[{version}] picks: {summary['picks']} made, {summary['settled']} settled, "
        f"record {summary['record']}, {summary['units']:+.2f} units "
        f"({summary['roi_pct']:+.1f}% ROI)",
        "  avg CLV: " + (f"{clv:+.2f}%" if clv is not None else "n/a")
        + "   avg line move in our favour: "
        + (f"{move:+.2f} pts" if move is not None else "n/a"),
        f"  {fair_close_text(summary)}",
    ]
    calibration = nba_paper.calibration_summary(settled, model_version=version)
    if calibration["n"] == 0:
        lines.append("  calibration: no settled lines yet.")
    else:
        lines.append(
            f"  calibration on {calibration['n']} lines: model {calibration['brier_model']:.4f}"
            f" vs market {calibration['brier_market']:.4f} (Brier, lower is better)")
    return lines


def publish_line(today: dt.date) -> str:
    """Publish the record; a failure is reported in the log but never fails the settle."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import publish_record
        return publish_record.run(today)
    except Exception as exc:       # noqa: BLE001 - see docstring
        detail = getattr(exc, "stderr", "") or exc
        return f"Record not published: {type(exc).__name__}: {str(detail).strip()[:200]}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    today = dt.datetime.now(nba_snapshot_plan.EASTERN).date()
    try:
        report = build_report(today)
    except Exception as exc:
        report = f"Settlement crashed: {type(exc).__name__}: {exc}"
        failed = True
    else:
        failed = False
    if args.publish and not failed:
        report += "\n\n" + publish_line(today)
    print(report)  # a no-op under pythonw, where there is no console
    if args.log_file is not None:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        with args.log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp}  settle\n{report}\n\n")
    first_line = report.splitlines()[0] if report else ""
    job_health.record("settle", job_health.FAILED if failed else job_health.OK, first_line[:200])
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
