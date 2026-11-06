"""Learn a correction for each model's chances, by player role, and check it honestly.

The calibration check (scripts/nba_calibration_by_line.py) found the models too sure about bench
players: a 70%+ chance for a player under 18 minutes came true far less often than said. This
fits, for every model and role, a curve from "what the model said" to "what happened", using
isotonic regression (it may only bend the chances, never reorder them).

Protocol, the same as for the models themselves:
1. Fit on 2024-25 predictions (from models trained on 2023-24).
2. Apply to 2025-26 predictions (from models trained on 2023-24 + 2024-25) and report, once,
   whether the corrected chances are closer to what happened.
3. The curves the app uses are then fitted on 2025-26, the most recent season, and saved to
   src/edgefinder/models/recalibration.json.

Usage:  python scripts/nba_recalibration_fit.py
"""

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from edgefinder.betting import negbin  # noqa: E402
from edgefinder.data import nba_stats  # noqa: E402
from edgefinder.models import (  # noqa: E402
    nba_baselines, nba_context, nba_context_points, nba_context_v2, nba_features, nba_minutes_points,
    nba_points, nba_recalibration)
from edgefinder.models.nba_shot_features import add_shot_features  # noqa: E402

import nba_context_eval as base  # noqa: E402
from nba_improve_eval import predict_variants  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[1] / "src" / "edgefinder" / "models" / "recalibration.json"
THRESHOLDS = list(range(3, 41))
MODELS = {   # ledger version -> (prediction column, spread)
    nba_points.MODEL_VERSION: ("pred_ewma", nba_points.MODEL_DISPERSION),
    nba_minutes_points.MODEL_VERSION: ("pts_minutes_v1", nba_minutes_points.MODEL_DISPERSION),
    nba_context_points.MODEL_VERSION: ("pts_context", nba_context_points.MODEL_DISPERSION),
    nba_context_v2.MODEL_VERSION: ("pts_blend_shots", nba_context_v2.MODEL_DISPERSION),
}
LOCK = 0.70


def recent_minutes(features: pd.DataFrame) -> pd.Series:
    """Average minutes over the player's previous 10 games (the game itself excluded)."""
    previous = features.groupby("player_id")["minutes"].shift(1)
    return previous.groupby(features["player_id"]).transform(
        lambda s: s.rolling(nba_recalibration.RECENT_GAMES, min_periods=3).mean())


def scored(features: pd.DataFrame, train: tuple, season: str) -> pd.DataFrame:
    needed = ["min_ewma_mid", "rate_ewma_05", "pred_ewma"]
    rows = base.rotation(features[features["season"] == season]).dropna(subset=needed)
    trained = features[features["season"].isin(train)]
    out = predict_variants(trained, rows)
    return out.join(base.predict_all(trained, rows)[["pts_minutes_v1"]])


def long_table(frame: pd.DataFrame, column: str, width) -> pd.DataFrame:
    means = frame[column].to_numpy()
    parts = []
    for k in THRESHOLDS:
        parts.append(pd.DataFrame({
            "chance": negbin.over_prob(k - 0.5, means, width),
            "hit": (frame["pts"].to_numpy() >= k).astype(float),
            "role": [nba_recalibration.role_for(m) for m in frame["recent_minutes"]]}))
    table = pd.concat(parts, ignore_index=True)
    return table[(table["chance"] >= 0.02) & (table["chance"] <= 0.98) & table["role"].notna()]


def fit_curves(table: pd.DataFrame) -> dict[str, dict]:
    curves = {}
    for role, part in table.groupby("role"):
        model = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(
            part["chance"], part["hit"])
        grid = nba_recalibration.GRID
        curves[role] = {"x": [round(float(x), 4) for x in grid],
                        "y": [round(float(y), 4) for y in model.predict(grid)]}
    return curves


def apply(table: pd.DataFrame, curves: dict) -> np.ndarray:
    out = table["chance"].to_numpy().copy()
    for role, curve in curves.items():
        mask = (table["role"] == role).to_numpy()
        out[mask] = np.interp(out[mask], curve["x"], curve["y"])
    return out


def report(table: pd.DataFrame, corrected: np.ndarray) -> pd.DataFrame:
    rows = []
    for role in nba_recalibration.ROLE_NAMES:
        part = table["role"] == role
        before, after, hit = table.loc[part, "chance"], corrected[part.to_numpy()], table.loc[part, "hit"]
        locks = before >= LOCK
        rows.append({
            "role": role, "lines": int(part.sum()),
            "brier before": float(np.mean((before - hit) ** 2)),
            "brier after": float(np.mean((after - hit) ** 2)),
            "locks: said": float(before[locks].mean()),
            "corrected to": float(after[locks.to_numpy()].mean()),
            "happened": float(hit[locks].mean())})
    return pd.DataFrame(rows)


def main() -> None:
    today = dt.date.today()
    games = pd.concat([nba_stats.load_season(s, today=today) for s in base.SEASONS],
                      ignore_index=True)
    features = add_shot_features(nba_context.add_context(nba_features.build_features(games), games))
    baseline = nba_baselines.add_baseline_predictions(games, "pts")[
        ["player_id", "game_id", "pred_ewma"]]
    features = features.merge(baseline, on=["player_id", "game_id"], how="left")
    features["recent_minutes"] = recent_minutes(features)

    validation = scored(features, base.SELECT_TRAIN, base.VALIDATE)
    test = scored(features, base.FINAL_TRAIN, base.TEST)
    production = {}
    for version, (column, width) in MODELS.items():
        fitted = fit_curves(long_table(validation, column, width))
        test_table = long_table(test, column, width)
        print(f"=== {version}: fitted on {base.VALIDATE}, scored once on {base.TEST} ===")
        print(report(test_table, apply(test_table, fitted)).round(4).to_string(index=False))
        print()
        production[version] = fit_curves(test_table)
    OUTPUT.write_text(json.dumps(production, indent=1), encoding="utf-8")
    print(f"Wrote the production curves (fitted on {base.TEST}) to {OUTPUT.name}")


if __name__ == "__main__":
    main()
