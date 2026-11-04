"""Walk-forward calibration backtest for the MLB Elo model.

Free — needs no odds data. Replays the season in order: predict each
game with only the games before it, then update. Reports Brier score,
log loss, and a calibration table against a home-advantage-only
baseline. If the model can't beat the baseline, its win probabilities
add nothing and MODEL_WEIGHT should stay low (or go lower).

Usage: python scripts/backtest_mlb.py [season]
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import mlb_api
from edgefinder.models import elo

BURN_IN_GAMES = 300  # early-season ratings are noise; don't score them


def main() -> None:
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    games = sorted(mlb_api.season_results(season), key=lambda g: g["date"])
    if len(games) <= BURN_IN_GAMES:
        print(f"Only {len(games)} completed games; need more than "
              f"{BURN_IN_GAMES} to evaluate.")
        return
    home_win_rate = sum(g["home_score"] > g["away_score"] for g in games) / len(games)
    model = elo.EloModel(k=elo.MLB_K, home_advantage=elo.MLB_HOME_ADVANTAGE)
    predictions = []
    for i, game in enumerate(games):
        prob = model.expected_home_win_prob(game["home"], game["away"])
        outcome = 1.0 if game["home_score"] > game["away_score"] else 0.0
        if i >= BURN_IN_GAMES:
            predictions.append((prob, outcome))
        model.update(elo.GameResult(game["home"], game["away"],
                                    game["home_score"], game["away_score"]))
    _report(predictions, home_win_rate, season, len(games))


def _report(predictions, home_win_rate: float, season: int, total: int) -> None:
    n = len(predictions)
    brier = sum((p - o) ** 2 for p, o in predictions) / n
    log_loss = -sum(o * math.log(p) + (1 - o) * math.log(1 - p)
                    for p, o in predictions) / n
    base_p = home_win_rate
    base_brier = sum((base_p - o) ** 2 for _, o in predictions) / n
    base_log_loss = -sum(o * math.log(base_p) + (1 - o) * math.log(1 - base_p)
                         for _, o in predictions) / n
    print(f"{season}: {total} games, {n} scored after {total - n} burn-in")
    print(f"League home win rate: {home_win_rate:.3f}\n")
    print(f"{'metric':<12}{'Elo model':>12}{'baseline':>12}   (lower is better)")
    print(f"{'Brier':<12}{brier:>12.4f}{base_brier:>12.4f}")
    print(f"{'Log loss':<12}{log_loss:>12.4f}{base_log_loss:>12.4f}")
    verdict = ("beats" if brier < base_brier else "DOES NOT beat")
    print(f"\nModel {verdict} the home-advantage-only baseline.\n")
    print("Calibration (model said X% -> home actually won Y%):")
    buckets: dict[int, list[float]] = {}
    for p, o in predictions:
        buckets.setdefault(int(p * 10), []).append(o)
    for bucket in sorted(buckets):
        outcomes = buckets[bucket]
        lo, hi = bucket * 10, bucket * 10 + 10
        actual = sum(outcomes) / len(outcomes)
        print(f"  {lo:>3}-{hi}%: actual {actual * 100:5.1f}%  "
              f"({len(outcomes)} games)")


if __name__ == "__main__":
    main()
