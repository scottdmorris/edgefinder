"""Does a learned minutes model beat the rolling-average baselines?

Protocol, fixed before looking at results:
1. Compare a few fixed model settings by training on 2023-24 and scoring
   minutes on 2024-25. Nothing is tuned on the test season.
2. Retrain the winner on 2023-24 + 2024-25 and score 2025-26, once.
3. Score on rotation players (20+ minutes last season), the same pool and
   metrics as nba_baseline_eval.py, so the numbers are comparable.

Points are projected as predicted minutes times the player's recent
points per minute. The oracle row uses each player's ACTUAL minutes: not a
real model, just the ceiling on what better minutes could ever buy.

Usage:  python scripts/nba_minutes_eval.py
"""

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import nba_stats  # noqa: E402
from edgefinder.eval import nba_eval  # noqa: E402
from edgefinder.models import nba_baselines, nba_features, nba_minutes  # noqa: E402

SEASONS = ("2022-23", "2023-24", "2024-25", "2025-26")
SELECT_TRAIN, SELECT_VALIDATE = ("2023-24",), "2024-25"
FINAL_TRAIN, TEST = ("2023-24", "2024-25"), "2025-26"
CONFIGS = {
    "shallow": {"max_depth": 3, "max_iter": 150, "min_samples_leaf": 100},
    "default": {},
    "deep": {"max_depth": 6, "max_iter": 300, "min_samples_leaf": 30},
}
MIN_PRIOR_MINUTES = 20.0


def rotation(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["prior_minutes"] >= MIN_PRIOR_MINUTES]


def minutes_mae(actual: pd.Series, predicted) -> float:
    return float(np.mean(np.abs(np.asarray(predicted) - actual.to_numpy())))


def main() -> None:
    today = dt.date.today()
    games = pd.concat([nba_stats.load_season(s, today=today) for s in SEASONS], ignore_index=True)
    features = nba_features.build_features(games)
    baseline = nba_baselines.add_baseline_predictions(games, "pts")[["player_id", "game_id", "pred_ewma"]]
    features = features.merge(baseline, on=["player_id", "game_id"], how="left")

    print("Step 1: choose model settings (train 2023-24, validate 2024-25, minutes MAE)")
    validation = rotation(features[features["season"] == SELECT_VALIDATE]).dropna(
        subset=["min_ewma_mid"])
    print(f"  naive recent-minutes average: {minutes_mae(validation['minutes'], validation['min_ewma_mid']):.3f}")
    scores = {}
    for name, params in CONFIGS.items():
        model = nba_minutes.MinutesModel(**params).fit(features[features["season"].isin(SELECT_TRAIN)])
        scores[name] = minutes_mae(validation["minutes"], model.predict(validation))
        print(f"  {name:8s} {scores[name]:.3f}")
    chosen = min(scores, key=scores.get)
    print(f"  -> using '{chosen}'\n")

    model = nba_minutes.MinutesModel(**CONFIGS[chosen]).fit(
        features[features["season"].isin(FINAL_TRAIN)])
    test = rotation(features[features["season"] == TEST]).dropna(
        subset=["min_ewma_mid", "rate_ewma_05", "pred_ewma"]).copy()
    test["pred_minutes"] = model.predict(test)
    test["pts_ewma_baseline"] = test["pred_ewma"]
    test["pts_recent_minutes_x_rate"] = nba_minutes.project_points(test, test["min_ewma_mid"].to_numpy())
    test["pts_learned_minutes_x_rate"] = nba_minutes.project_points(test, test["pred_minutes"].to_numpy())
    test["pts_oracle_minutes_x_rate"] = nba_minutes.project_points(test, test["minutes"].to_numpy())

    print(f"Step 2: {TEST}, {len(test):,} rotation player-games, trained on {model.n_train:,} rows\n")
    print("Minutes accuracy (MAE in minutes; actual minutes have sd "
          f"{test['minutes'].std():.2f}):")
    print(f"  recent-minutes average  {minutes_mae(test['minutes'], test['min_ewma_mid']):.3f}")
    print(f"  learned model           {minutes_mae(test['minutes'], test['pred_minutes']):.3f}\n")

    methods = ["pts_ewma_baseline", "pts_recent_minutes_x_rate",
               "pts_learned_minutes_x_rate", "pts_oracle_minutes_x_rate"]
    print("Points accuracy:")
    table = nba_eval.compare_methods(test, methods, "pts")[
        ["mae", "rmse", "bias", "log_score", "cov50", "cov80"]]
    print(table.round(4).to_string(), "\n")

    print("Points MAE by situation (does the learned model help where roles change?):")
    situations = {
        "recently missed 2+ games": test["missed_last10"] >= 2,
        "back-to-back": test["is_b2b"] == 1.0,
        "everything else": ~((test["missed_last10"] >= 2) | (test["is_b2b"] == 1.0)),
    }
    rows = {}
    for label, mask in situations.items():
        subset = test[mask]
        rows[label] = {"n": len(subset)} | {
            m.replace("pts_", ""): float(np.mean(np.abs(subset[m] - subset["pts"])))
            for m in methods[:3]}
    print(pd.DataFrame(rows).T.round(3).to_string())


if __name__ == "__main__":
    main()
