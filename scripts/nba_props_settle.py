"""Settle finished NBA prop games and report how the model is doing.

Grades picks at a flat 1 unit, voids lines for players who didn't play,
attaches closing-line movement, then reports:
- the record, units and closing-line value of the picks
- Brier scores of the model vs the market's own devigged probability on
  EVERY settled line (the model only has something to offer if it wins)

Usage:  python scripts/nba_props_settle.py [--log-file PATH]
  --log-file  also append the report to PATH (scheduled runs have no console)
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import nba_props, nba_snapshot_plan, nba_stats  # noqa: E402
from edgefinder.tracking import nba_paper  # noqa: E402


def build_report(today: dt.date) -> str:
    ledger = nba_paper.load_ledger()
    if ledger.empty:
        return "The ledger is empty: run scripts/nba_props_snapshot.py first."
    games = nba_stats.load_season(nba_stats.current_season(today), today=today)
    settled = nba_paper.settle(ledger, games, nba_props.load_snapshots(), today)
    nba_paper.save_ledger(settled)

    lines = [f"Ledger: {len(settled)} lines  {settled['status'].value_counts().to_dict()}"]
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
    return "\n".join(lines)


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
    ]
    calibration = nba_paper.calibration_summary(settled, model_version=version)
    if calibration["n"] == 0:
        lines.append("  calibration: no settled lines yet.")
    else:
        lines.append(
            f"  calibration on {calibration['n']} lines: model {calibration['brier_model']:.4f}"
            f" vs market {calibration['brier_market']:.4f} (Brier, lower is better)")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--log-file", type=Path)
    args = parser.parse_args()
    today = dt.datetime.now(nba_snapshot_plan.EASTERN).date()
    try:
        report = build_report(today)
    except Exception as exc:
        report = f"Settlement crashed: {type(exc).__name__}: {exc}"
        failed = True
    else:
        failed = False
    print(report)  # a no-op under pythonw, where there is no console
    if args.log_file is not None:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        with args.log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp}  settle\n{report}\n\n")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
