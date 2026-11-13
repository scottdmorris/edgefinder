"""Does knowing the game (who should win, by how much, how many points) improve the
points model beyond `context-v2`?

Protocol, fixed before looking at results (same discipline as nba_improve_eval.py):
1. Choose between variants and form windows by training on 2023-24 and scoring 2024-25.
2. Retrain the chosen variant on 2023-24 + 2024-25 and score 2025-26, once.
3. Rotation players only (20+ minutes last season).

The champion is context-v2's blend: the average of the direct model with shot inputs
and the minutes-times-rate model that knows who is out.

Variants (the game numbers come from nba_game_context, all from earlier games):
  game_direct    the direct model also gets the game numbers; minutes side unchanged
  game_minutes   the minutes model also gets them (a blowout cuts minutes); direct unchanged
  game_both      both sides get them

Usage:  python scripts/nba_game_context_eval.py
"""

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import nba_stats  # noqa: E402
from edgefinder.eval import nba_eval  # noqa: E402
from edgefinder.models import (  # noqa: E402
    nba_baselines, nba_context, nba_features, nba_game_context, nba_minutes)
from edgefinder.models.nba_shot_features import SHOT_COLUMNS, add_shot_features  # noqa: E402

import nba_context_eval as base  # noqa: E402  (same folder: reuse the exact setup)

WINDOWS = (10, 25)
GAME = nba_game_context.GAME_COLUMNS
DIRECT = base.DIRECT_CONTEXT + SHOT_COLUMNS
CHAMPION = "pts_champion"
VARIANTS = ["pts_game_direct", "pts_game_minutes", "pts_game_both"]
BLOWOUT_MARGIN = 8.0


def predict_variants(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    out = test.copy()
    direct = {}
    for name, columns in (("plain", DIRECT), ("game", DIRECT + GAME)):
        model, kept = base.fit_direct(train, columns)
        direct[name] = np.clip(model.predict(out[kept]), 0.05, None)
    minutes = {}
    for name, columns in (("plain", base.MINUTES_WITH_ABSENCES),
                          ("game", base.MINUTES_WITH_ABSENCES + GAME)):
        model = nba_minutes.MinutesModel(features=columns).fit(train)
        out[f"min_{name}"] = model.predict(out)
        minutes[name] = nba_minutes.project_points(out, out[f"min_{name}"])
    out[CHAMPION] = (direct["plain"] + minutes["plain"]) / 2.0
    out["pts_game_direct"] = (direct["game"] + minutes["plain"]) / 2.0
    out["pts_game_minutes"] = (direct["plain"] + minutes["game"]) / 2.0
    out["pts_game_both"] = (direct["game"] + minutes["game"]) / 2.0
    return out


def log_score(frame: pd.DataFrame, method: str) -> float:
    return nba_eval.score_predictions(frame, method, "pts")["log_score"]


def build(games: pd.DataFrame, window: int) -> pd.DataFrame:
    features = nba_context.add_context(nba_features.build_features(games), games)
    features = add_shot_features(features)
    features = nba_game_context.add_game_context(features, games, window=window)
    baseline = nba_baselines.add_baseline_predictions(games, "pts")[
        ["player_id", "game_id", "pred_ewma"]]
    return features.merge(baseline, on=["player_id", "game_id"], how="left")


def main() -> None:
    today = dt.date.today()
    games = pd.concat([nba_stats.load_season(s, today=today) for s in base.SEASONS],
                      ignore_index=True)
    needed = ["min_ewma_mid", "rate_ewma_05", "pred_ewma"]
    methods = [CHAMPION] + VARIANTS

    print("Step 1: choose (train 2023-24, validate 2024-25)")
    built, choice = {}, None
    for window in WINDOWS:
        built[window] = build(games, window)
        features = built[window]
        validation = base.rotation(features[features["season"] == base.VALIDATE]).dropna(subset=needed)
        scored = predict_variants(features[features["season"].isin(base.SELECT_TRAIN)], validation)
        base.report(f"  form window {window}: {len(scored):,} rotation player-games", scored, methods)
        for method in VARIANTS:
            gain = log_score(scored, method) - log_score(scored, CHAMPION)
            if choice is None or gain > choice[0]:
                choice = (gain, window, method)
    _, window, best = choice
    print(f"  -> best on validation by log score: {best}, form window {window}\n")

    print(f"Step 2: {base.TEST}, scored once (train 2023-24 + 2024-25)")
    features = built[window]
    test = base.rotation(features[features["season"] == base.TEST]).dropna(subset=needed)
    final = predict_variants(features[features["season"].isin(base.FINAL_TRAIN)], test)
    base.report(f"  {len(final):,} rotation player-games", final, methods)

    print("Improvement over context-v2 in points of MAE (positive = better), 95% interval:")
    for method in VARIANTS:
        gain, low, high = base.paired_ci(final, method, CHAMPION)
        verdict = "real" if low > 0 else "not distinguishable from zero" if high > 0 else "worse"
        chosen = "  <- chosen on validation" if method == best else ""
        print(f"  {method:18s} {gain:+.4f}  [{low:+.4f}, {high:+.4f}]  {verdict}{chosen}")

    print(f"\nWhere the game numbers should matter most (points MAE, {best}):")
    lopsided = final["exp_margin"].abs() >= BLOWOUT_MARGIN
    for label, mask in ((f"expected margin {BLOWOUT_MARGIN:.0f}+ either way", lopsided),
                        ("closer games", ~lopsided)):
        subset = final[mask]
        print(f"  {label:32s} n={len(subset):6,}  champion {base.mae(subset, CHAMPION):.4f}  "
              f"challenger {base.mae(subset, best):.4f}")

    minutes_mae = {name: float(np.mean(np.abs(final[f"min_{name}"] - final["minutes"])))
                   for name in ("plain", "game")}
    print(f"\nMinutes error: without the game numbers {minutes_mae['plain']:.4f}, "
          f"with them {minutes_mae['game']:.4f}")

    actual_margin = final.groupby(["game_id", "team"]).agg(
        exp=("exp_margin", "first")).reset_index()
    print(f"Expected margin, {actual_margin['exp'].notna().mean():.0%} of team-games have one; "
          f"typical size {actual_margin['exp'].abs().median():.1f} points")


if __name__ == "__main__":
    main()
