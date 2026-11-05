"""Do teammate absences and opponent/pace information improve the points model?

Protocol, fixed before looking at results (the same discipline as the minutes
model):
1. Choose between model variants by training on 2023-24 and scoring 2024-25.
2. Retrain the winner on 2023-24 + 2024-25 and score 2025-26, once.
3. Rotation players only (20+ minutes last season), the same pool as the
   other evaluation scripts.

Variants (all start from information available before tip-off):
  minutes-v1         current model: predicted minutes x recent scoring rate
  minutes + absences same, but the minutes model also knows who is out
  direct             one model predicts points directly, from the same inputs
  direct + context   the same, plus absences, opponent defense and pace

Also reports the points error where a rotation teammate was out, since that's
where absence information should matter.

Usage:  python scripts/nba_context_eval.py
"""

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.betting import negbin  # noqa: E402
from edgefinder.data import nba_stats  # noqa: E402
from edgefinder.eval import nba_eval  # noqa: E402
from edgefinder.models import (  # noqa: E402
    nba_baselines, nba_context, nba_features, nba_minutes)

SEASONS = ("2022-23", "2023-24", "2024-25", "2025-26")
SELECT_TRAIN, VALIDATE = ("2023-24",), "2024-25"
FINAL_TRAIN, TEST = ("2023-24", "2024-25"), "2025-26"
MIN_PRIOR_MINUTES = 20.0
RATE_COLUMNS = ["rate_ewma_05", "rate_ewma_10"]
DIRECT_BASE = nba_minutes.MINUTES_FEATURES + RATE_COLUMNS
DIRECT_CONTEXT = DIRECT_BASE + nba_context.CONTEXT_COLUMNS
MINUTES_WITH_ABSENCES = nba_minutes.MINUTES_FEATURES + nba_context.ABSENCE_COLUMNS
DIRECT_PARAMS = {"loss": "poisson", "max_iter": 200, "learning_rate": 0.05, "max_depth": 4,
                 "min_samples_leaf": 50, "l2_regularization": 1.0, "random_state": 0}
BOOTSTRAPS = 400


def rotation(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["prior_minutes"] >= MIN_PRIOR_MINUTES]


def fit_direct(train: pd.DataFrame, columns: list[str]):
    usable = train[train["min_ewma_mid"].notna() & train["pts"].notna()]
    kept = [c for c in columns if usable[c].notna().any()]
    return HistGradientBoostingRegressor(**DIRECT_PARAMS).fit(usable[kept], usable["pts"]), kept


def predict_all(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """Every variant's points prediction for the test rows."""
    out = test.copy()
    out["pts_baseline_ewma"] = out["pred_ewma"]
    base_minutes = nba_minutes.MinutesModel().fit(train)
    out["pts_minutes_v1"] = nba_minutes.project_points(out, base_minutes.predict(out))
    aware = nba_minutes.MinutesModel(features=MINUTES_WITH_ABSENCES).fit(train)
    out["pts_minutes_absences"] = nba_minutes.project_points(out, aware.predict(out))
    for name, columns in (("direct", DIRECT_BASE), ("direct_context", DIRECT_CONTEXT)):
        model, kept = fit_direct(train, columns)
        out[f"pts_{name}"] = np.clip(model.predict(out[kept]), 0.05, None)
    return out


def mae(frame: pd.DataFrame, column: str) -> float:
    return float(np.mean(np.abs(frame[column] - frame["pts"])))


def paired_ci(frame: pd.DataFrame, challenger: str, champion: str) -> tuple[float, float, float]:
    """MAE improvement of the challenger over the champion (positive = better),
    with a 95% interval from resampling players, not games, since one player's
    games are not independent of each other."""
    rng = np.random.default_rng(0)
    by_player = {pid: g for pid, g in frame.groupby("player_id")}
    ids = np.array(list(by_player))
    saved = (frame[champion] - frame["pts"]).abs() - (frame[challenger] - frame["pts"]).abs()
    per_player = saved.groupby(frame["player_id"]).agg(["sum", "count"])
    draws = []
    for _ in range(BOOTSTRAPS):
        picked = per_player.loc[rng.choice(ids, len(ids), replace=True)]
        draws.append(picked["sum"].sum() / picked["count"].sum())
    return float(saved.mean()), float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def report(title: str, frame: pd.DataFrame, methods: list[str]) -> None:
    print(title)
    table = nba_eval.compare_methods(frame, methods, "pts")[["mae", "rmse", "bias", "log_score"]]
    print(table.round(4).to_string(), "\n")


def main() -> None:
    today = dt.date.today()
    games = pd.concat([nba_stats.load_season(s, today=today) for s in SEASONS], ignore_index=True)
    features = nba_features.build_features(games)
    features = nba_context.add_context(features, games)
    baseline = nba_baselines.add_baseline_predictions(games, "pts")[
        ["player_id", "game_id", "pred_ewma"]]
    features = features.merge(baseline, on=["player_id", "game_id"], how="left")
    needed = ["min_ewma_mid", "rate_ewma_05", "pred_ewma"]
    methods = ["pts_baseline_ewma", "pts_minutes_v1", "pts_minutes_absences", "pts_direct",
               "pts_direct_context"]

    print("Step 1: choose between variants (train 2023-24, validate 2024-25)")
    validation = rotation(features[features["season"] == VALIDATE]).dropna(subset=needed)
    scored = predict_all(features[features["season"].isin(SELECT_TRAIN)], validation)
    report(f"  {len(scored):,} rotation player-games", scored, methods)
    maes = {m: mae(scored, m) for m in methods[1:]}
    best = min(maes, key=maes.get)
    print(f"  -> best on validation: {best}\n")

    print(f"Step 2: {TEST}, scored once (train 2023-24 + 2024-25)")
    test = rotation(features[features["season"] == TEST]).dropna(subset=needed)
    final = predict_all(features[features["season"].isin(FINAL_TRAIN)], test)
    report(f"  {len(final):,} rotation player-games", final, methods)

    print("Improvement over minutes-v1, in points of MAE (positive = better), 95% interval "
          "from resampling players:")
    for method in methods[2:]:
        gain, low, high = paired_ci(final, method, "pts_minutes_v1")
        verdict = "real" if low > 0 else "not distinguishable from zero" if high > 0 else "worse"
        print(f"  {method:22s} {gain:+.4f}  [{low:+.4f}, {high:+.4f}]  {verdict}")

    print("\nWhere a rotation teammate was out versus not (points MAE):")
    out_mask = final["lost_min"] >= 20.0
    rows = {}
    for label, mask in (("a rotation teammate was out", out_mask), ("everyone available", ~out_mask)):
        subset = final[mask]
        rows[label] = {"n": len(subset)} | {m.replace("pts_", ""): mae(subset, m) for m in methods}
    print(pd.DataFrame(rows).T.round(3).to_string())

    print("\nNegative-binomial dispersion measured on these out-of-sample predictions "
          "(what MODEL_DISPERSION should be):")
    for method in ("pts_minutes_v1", "pts_direct_context"):
        spread = negbin.estimate_dispersion(final[method], final["pts"])
        print(f"  {method:22s} {spread:.2f}")

    print(f"\nBest single variant on {TEST}: "
          f"{min(methods[1:], key=lambda m: mae(final, m)).replace('pts_', '')}")


if __name__ == "__main__":
    main()
