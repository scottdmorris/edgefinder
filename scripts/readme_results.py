"""Print the live record as a Markdown table, for pasting into the README.

Numbers come straight from the ledger (FanDuel points picks that have been graded), so the
README never says more than the record does. Re-run it and paste when updating.

Usage:  python scripts/readme_results.py
"""

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.tracking import nba_paper, nba_parlay  # noqa: E402


def table(ledger: pd.DataFrame) -> str:
    """One row per model: graded picks, record, units, and how often the price moved our way."""
    graded = ledger[(ledger["book"] == "fanduel") & (ledger["stat"] == "points")
                    & (ledger["status"] == "settled") & ledger["pick_side"].notna()]
    rows = ["| Model | Graded picks | Record | Units | Beat the closing price |",
            "|---|---:|---:|---:|---:|"]
    for version in sorted(graded["model_version"].dropna().unique()):
        picks = graded[graded["model_version"] == version]
        clv = pd.to_numeric(picks["clv_pct"], errors="coerce").dropna()
        wins, losses = int((picks["result"] == "win").sum()), int((picks["result"] == "loss").sum())
        units = float(pd.to_numeric(picks["pnl_units"], errors="coerce").sum())
        beat = f"{(clv > 0).mean() * 100:.0f}% of {len(clv)}" if len(clv) else "n/a"
        rows.append(f"| {nba_parlay.short_model_name(version)} (`{version}`) | {len(picks)} | "
                    f"{wins}-{losses} | {units:+.2f} | {beat} |")
    if len(rows) == 2:
        rows.append("| none graded yet | | | | |")
    return "\n".join(rows)


def main() -> None:
    ledger = nba_paper.load_ledger()
    days = sorted(ledger.loc[ledger["status"] == "settled", "game_date"].unique())
    print(table(ledger))
    print(f"\nGame days graded: {len(days)} ({days[0]} to {days[-1]})" if days
          else "\nNo game days graded yet.")
    print(f"As of {dt.date.today().isoformat()}.")


if __name__ == "__main__":
    main()
