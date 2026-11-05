"""Can the points model be improved beyond `context-v1`?

Protocol, fixed before looking at results (same discipline as nba_context_eval.py):
1. Choose between variants by training on 2023-24 and scoring 2024-25.
2. Retrain the chosen variant on 2023-24 + 2024-25 and score 2025-26, once.
3. Rotation players only (20+ minutes last season).

Ideas tried (all use only information from before the game being predicted):
  shots      add how often the player shoots and gets to the line (shots and free
             throws per minute, smoothed), how steady his scoring has been, and his
             season-to-date scoring rate. Attempts are steadier than points.
  blend      average the direct context model with the minutes-times-rate model
             that also knows who is out. Two different views of the same game.
  spread     keep the mean as it is but let the uncertainty depend on the size of the
             projection (a 28-point projection is wider than a 9-point one), with the
             widths measured on 2024-25 and applied to 2025-26.

Usage:  python scripts/nba_improve_eval.py
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
from edgefinder.models.nba_shot_features import SHOT_COLUMNS, add_shot_features  # noqa: E402

import nba_context_eval as base  # noqa: E402  (same folder: reuse the exact setup)

SPREAD_BINS = (0, 8, 12, 17, 22, 10_000)


def predict_variants(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    out = test.copy()
    for name, columns in (("context", base.DIRECT_CONTEXT),
                          ("shots", base.DIRECT_CONTEXT + SHOT_COLUMNS)):
        model, kept = base.fit_direct(train, columns)
        out[f"pts_{name}"] = np.clip(model.predict(out[kept]), 0.05, None)
    aware = nba_minutes.MinutesModel(features=base.MINUTES_WITH_ABSENCES).fit(train)
    out["pts_minutes_absences"] = nba_minutes.project_points(out, aware.predict(out))
    out["pts_blend_context"] = (out["pts_context"] + out["pts_minutes_absences"]) / 2.0
    out["pts_blend_shots"] = (out["pts_shots"] + out["pts_minutes_absences"]) / 2.0
    return out


def spread_table(frame: pd.DataFrame, column: str) -> pd.Series:
    """Dispersion per band of projected points, measured on the frame given."""
    bands = pd.cut(frame[column], SPREAD_BINS, include_lowest=True)
    return frame.groupby(bands, observed=True).apply(
        lambda g: negbin.estimate_dispersion(g[column], g["pts"]), include_groups=False)


def band_log_score(frame: pd.DataFrame, column: str, table: pd.Series) -> float:
    bands = pd.cut(frame[column], SPREAD_BINS, include_lowest=True)
    dispersion = bands.map(table).astype(float).fillna(table.median())
    return float(np.mean(negbin.logpmf(np.rint(frame["pts"]), frame[column], dispersion)))


def knots(frame: pd.DataFrame, column: str) -> tuple[list[float], list[float]]:
    """(mean projection, dispersion) per band: the points a smooth width is drawn through."""
    bands = pd.cut(frame[column], SPREAD_BINS, include_lowest=True)
    groups = [g for _, g in frame.groupby(bands, observed=True)]
    return ([float(g[column].mean()) for g in groups],
            [float(negbin.estimate_dispersion(g[column], g["pts"])) for g in groups])


def smooth_log_score(frame: pd.DataFrame, column: str, points) -> float:
    width = negbin.varying(*points)
    return float(np.mean(negbin.logpmf(np.rint(frame["pts"]), frame[column], width)))


def fixed_log_score(frame: pd.DataFrame, column: str, dispersion: float) -> float:
    return float(np.mean(negbin.logpmf(np.rint(frame["pts"]), frame[column], dispersion)))


def main() -> None:
    today = dt.date.today()
    games = pd.concat([nba_stats.load_season(s, today=today) for s in base.SEASONS],
                      ignore_index=True)
    features = nba_features.build_features(games)
    features = nba_context.add_context(features, games)
    features = add_shot_features(features)
    baseline = nba_baselines.add_baseline_predictions(games, "pts")[
        ["player_id", "game_id", "pred_ewma"]]
    features = features.merge(baseline, on=["player_id", "game_id"], how="left")
    needed = ["min_ewma_mid", "rate_ewma_05", "pred_ewma"]
    methods = ["pts_context", "pts_shots", "pts_blend_context", "pts_blend_shots"]

    print("Step 1: choose (train 2023-24, validate 2024-25)")
    validation = base.rotation(features[features["season"] == base.VALIDATE]).dropna(subset=needed)
    scored = predict_variants(features[features["season"].isin(base.SELECT_TRAIN)], validation)
    base.report(f"  {len(scored):,} rotation player-games", scored, methods)
    best = max(methods, key=lambda m: nba_eval.score_predictions(scored, m, "pts")["log_score"])
    print(f"  -> best on validation by log score: {best}\n")
    table = spread_table(scored, best)
    print("  dispersion by projected-points band (measured on validation):")
    print(table.round(2).to_string(), "\n")

    print(f"Step 2: {base.TEST}, scored once (train 2023-24 + 2024-25)")
    test = base.rotation(features[features["season"] == base.TEST]).dropna(subset=needed)
    final = predict_variants(features[features["season"].isin(base.FINAL_TRAIN)], test)
    base.report(f"  {len(final):,} rotation player-games", final, methods)

    print("Improvement over context-v1 in points of MAE (positive = better), 95% interval:")
    for method in methods[1:]:
        gain, low, high = base.paired_ci(final, method, "pts_context")
        verdict = "real" if low > 0 else "not distinguishable from zero" if high > 0 else "worse"
        print(f"  {method:20s} {gain:+.4f}  [{low:+.4f}, {high:+.4f}]  {verdict}")

    flat = negbin.estimate_dispersion(final[best], final["pts"])
    print(f"\nUncertainty on the chosen model ({best}), log score (higher is better):")
    print(f"  one fixed width ({base.nba_eval.negbin.estimate_dispersion(scored[best], scored['pts']):.2f} "
          f"from validation): {fixed_log_score(final, best, negbin.estimate_dispersion(scored[best], scored['pts'])):.4f}")
    print(f"  width by projection band, from validation:    {band_log_score(final, best, table):.4f}")
    print(f"  smooth width through the validation points:   "
          f"{smooth_log_score(final, best, knots(scored, best)):.4f}")
    print(f"  (for reference, width fitted on the test season itself: "
          f"{fixed_log_score(final, best, flat):.4f})")
    means, widths = knots(final, "pts_blend_shots")
    print("\nProduction knots, measured on the 2025-26 predictions of pts_blend_shots "
          "(what context-v2 uses, as context-v1 did):")
    print("  MEANS =", [round(m, 2) for m in means])
    print("  WIDTHS =", [round(w, 2) for w in widths])


if __name__ == "__main__":
    main()
