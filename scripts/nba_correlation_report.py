"""Measure how much players' points in the same game move together.

Prints the teammate and opponent correlation of rolling-average prediction
misses for each recent season, which is where TEAMMATE_RHO and
OPPONENT_RHO in betting/correlated.py come from. Uses cached game logs.

Usage:  python scripts/nba_correlation_report.py
"""

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import nba_stats  # noqa: E402
from edgefinder.models import nba_baselines, nba_correlation, nba_points  # noqa: E402

HISTORY_SEASONS = 4


def main() -> None:
    today = dt.datetime.now().date()
    seasons = nba_stats.recent_seasons(today, HISTORY_SEASONS)
    games = pd.concat([nba_stats.load_season(s, today=today) for s in seasons],
                      ignore_index=True)
    predicted = nba_baselines.add_baseline_predictions(games, "pts")
    for season in seasons:
        subset = predicted[predicted["season"] == season]
        misses = nba_correlation.standardised_misses(subset, nba_points.MODEL_DISPERSION)
        if misses.empty:
            continue  # the current season may not have enough games yet
        result = nba_correlation.pair_correlations(misses)
        print(f"{season}  teammates {result['teammate']:+.3f} "
              f"({result['teammate_pairs']:,} pairs)   opponents {result['opponent']:+.3f} "
              f"({result['opponent_pairs']:,} pairs)")


if __name__ == "__main__":
    main()
