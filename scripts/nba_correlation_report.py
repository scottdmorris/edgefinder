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
from edgefinder.models import (  # noqa: E402
    nba_baselines, nba_correlation, nba_points, nba_stat_model)

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


CROSS_STATS = {"points": ("pts", 10.0), "rebounds": ("reb", 4.0), "assists": ("ast", 3.0),
               "threes": ("fg3m", 1.5)}      # stat -> (game-log column, smallest projection kept)


def cross_report() -> None:
    """Correlation between DIFFERENT stats in the same game (what mixed slips need)."""
    from itertools import combinations
    today = dt.datetime.now().date()
    seasons = nba_stats.recent_seasons(today, HISTORY_SEASONS)
    games = pd.concat([nba_stats.load_season(s, today=today) for s in seasons],
                      ignore_index=True)
    misses = {}
    for stat, (column, smallest) in CROSS_STATS.items():
        predicted = nba_baselines.add_baseline_predictions(games, column)
        misses[stat] = nba_correlation.standardised_misses(
            predicted, nba_stat_model.STATS[stat].dispersion, stat=column,
            min_projection=smallest)
    print("\nDifferent stats in the same game (all seasons together):")
    for a, b in combinations(CROSS_STATS, 2):
        r = nba_correlation.cross_pair_correlations(misses[a], misses[b])
        print(f"  {a:9s} x {b:9s} same player {r['same_player']:+.3f} ({r['same_player_pairs']:,})"
              f"   teammates {r['teammate']:+.3f}   opponents {r['opponent']:+.3f}")


if __name__ == "__main__":
    main()
    cross_report()
