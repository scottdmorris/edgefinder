"""Is the model honest about every kind of line, or only on average?

When the model says a player has an 81% chance of scoring 6+, does that happen about 81% of the
time? This checks it on a season the models never trained on (2025-26, after training on the two
before), for every whole-number line from 3+ to 40+, split by:
- the player's role, from his minutes before the game (bench, rotation, starter), and
- how sure the model was (its chance in bands of 10 points).

The "locks" (a 70%+ chance on a low line for a bench player, like "Portis 6+") are where a
parlay is most exposed, so they are reported on their own. Both spreads are compared: one fixed
width for everybody (context-v1) and the width that grows with the projection (context-v2).

Usage:  python scripts/nba_calibration_by_line.py
"""

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from edgefinder.betting import negbin  # noqa: E402
from edgefinder.data import nba_stats  # noqa: E402
from edgefinder.models import (  # noqa: E402
    nba_baselines, nba_context, nba_context_points, nba_context_v2, nba_features)
from edgefinder.models.nba_shot_features import add_shot_features  # noqa: E402

import nba_context_eval as base  # noqa: E402
from nba_improve_eval import predict_variants  # noqa: E402

THRESHOLDS = list(range(3, 41))
ROLES = [("bench (under 18 min)", 0, 18), ("rotation (18-28 min)", 18, 28),
         ("starter (28+ min)", 28, 99)]
BANDS = np.arange(0.0, 1.0001, 0.1)
LOCK = 0.70


def long_table(frame: pd.DataFrame, mean_col: str, width) -> pd.DataFrame:
    """One row per player-game and line: the model's chance of reaching it, and whether he did."""
    means = frame[mean_col].to_numpy()
    rows = []
    for k in THRESHOLDS:
        chance = negbin.over_prob(k - 0.5, means, width)
        rows.append(pd.DataFrame({"threshold": k, "chance": chance,
                                  "hit": (frame["pts"].to_numpy() >= k).astype(float),
                                  "minutes": frame["min_ewma_mid"].to_numpy()}))
    table = pd.concat(rows, ignore_index=True)
    # a line nobody would bet (a 1% or 99.9% chance) says little about calibration
    return table[(table["chance"] >= 0.02) & (table["chance"] <= 0.98)]


def role_of(minutes: pd.Series) -> pd.Series:
    labels = pd.Series("unknown", index=minutes.index)
    for name, low, high in ROLES:
        labels[(minutes >= low) & (minutes < high)] = name
    return labels


def reliability(table: pd.DataFrame) -> pd.DataFrame:
    """Per role and chance band: lines, what the model said on average, and what happened."""
    table = table.assign(role=role_of(table["minutes"]),
                         band=pd.cut(table["chance"], BANDS, include_lowest=True))
    out = table.groupby(["role", "band"], observed=True).agg(
        lines=("hit", "size"), said=("chance", "mean"), happened=("hit", "mean")).reset_index()
    out["gap"] = out["happened"] - out["said"]
    return out


def lock_report(table: pd.DataFrame) -> pd.DataFrame:
    locks = table[table["chance"] >= LOCK].assign(role=role_of(table["minutes"]))
    out = locks.groupby("role").agg(lines=("hit", "size"), said=("chance", "mean"),
                                    happened=("hit", "mean")).reset_index()
    out["gap"] = out["happened"] - out["said"]
    return out


def main() -> None:
    today = dt.date.today()
    games = pd.concat([nba_stats.load_season(s, today=today) for s in base.SEASONS],
                      ignore_index=True)
    features = add_shot_features(nba_context.add_context(nba_features.build_features(games), games))
    baseline = nba_baselines.add_baseline_predictions(games, "pts")[
        ["player_id", "game_id", "pred_ewma"]]
    features = features.merge(baseline, on=["player_id", "game_id"], how="left")
    needed = ["min_ewma_mid", "rate_ewma_05", "pred_ewma"]
    test = base.rotation(features[features["season"] == base.TEST]).dropna(subset=needed)
    scored = predict_variants(features[features["season"].isin(base.FINAL_TRAIN)], test)
    print(f"{len(scored):,} player-games from {base.TEST}, never seen in training\n")

    for name, column, width in (
            ("context-v1 (one fixed width)", "pts_context", nba_context_points.MODEL_DISPERSION),
            ("context-v2 (width grows with projection)", "pts_blend_shots",
             nba_context_v2.MODEL_DISPERSION)):
        table = long_table(scored, column, width)
        print(f"=== {name}: {len(table):,} player-lines ===")
        print("Locks (model chance 70% or more):")
        print(lock_report(table).round(3).to_string(index=False))
        print("\nBy role and how sure the model was (gap = happened - said; negative = overconfident):")
        rel = reliability(table)
        rel = rel[rel["lines"] >= 300]
        print(rel.assign(band=rel["band"].astype(str)).round(3).to_string(index=False))
        print()


if __name__ == "__main__":
    main()
