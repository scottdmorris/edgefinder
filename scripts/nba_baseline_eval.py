"""Walk-forward scores for the NBA rolling-average baselines.

Usage:  python scripts/nba_baseline_eval.py [STAT] [SEASON]
  STAT    pts | reb | ast | fg3m   (default pts)
  SEASON  e.g. 2025-26             (default: the last completed season)

Every prediction uses only earlier games. The prior season supplies the
shrinkage prior, and only players who averaged 20+ minutes LAST season
are scored (roughly the players that prop markets list).
"""

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import nba_stats  # noqa: E402
from edgefinder.eval import nba_eval  # noqa: E402
from edgefinder.models import nba_baselines  # noqa: E402

PRED_COLS = ["pred_season_to_date", "pred_shrunk", "pred_last10", "pred_ewma"]
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def main() -> None:
    stat = sys.argv[1].lower() if len(sys.argv) > 1 else "pts"
    if stat not in STATS:
        sys.exit(f"STAT must be one of {', '.join(STATS)}")
    today = dt.date.today()
    target = sys.argv[2] if len(sys.argv) > 2 else nba_stats.previous_season(
        nba_stats.current_season(today))

    games = pd.concat(
        [nba_stats.load_season(season, today=today)
         for season in (nba_stats.previous_season(target), target)],
        ignore_index=True,
    )
    predictions = nba_baselines.add_baseline_predictions(games, stat)
    scored = nba_eval.rotation_players(predictions[predictions["season"] == target])
    common = scored.dropna(subset=PRED_COLS)

    print(f"\n{stat.upper()} baselines, {target} "
          f"({len(common):,} rotation player-games, all methods scored on the same rows)\n")
    table = nba_eval.compare_methods(common, PRED_COLS, stat)
    print(table.round({"mae": 3, "rmse": 3, "bias": 3, "dispersion": 1,
                       "log_score": 4, "cov50": 3, "cov80": 3}).to_string())
    print("\nMAE by games already played this season "
          "(first games included for methods that can predict them):\n")
    print(nba_eval.score_by_games_played(scored, PRED_COLS, stat).round(3).to_string())


if __name__ == "__main__":
    main()
