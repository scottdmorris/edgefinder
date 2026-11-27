"""Test whether recent exact-line hit rates improve held-out NBA points probabilities.

Run after downloading the archive used by nba_kalshi_backtest.py.
Uses Simple/Smarter projections made with pregame information and market quotes
from the same archive. Fits on early game nights and scores later nights once.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import nba_kalshi_backtest as archive  # noqa: E402

from edgefinder.data import nba_stats  # noqa: E402
from edgefinder.tracking import prop_history  # noqa: E402

WINDOWS = (*prop_history.WINDOWS, "season")
PRIOR_GAMES = 10


def history_features(frame: pd.DataFrame, games: pd.DataFrame) -> np.ndarray:
    grouped = {pid: prop_history.played_games(rows, "pts") for pid, rows in games.groupby("player_id")}
    empty = prop_history.played_games(pd.DataFrame(), "pts")
    results = []
    for row in frame.itertuples():
        counts = prop_history.line_counts(grouped.get(row.player_id, empty), "pts",
                                          pd.Timestamp(row.game_date), row.threshold - 0.5)
        # Shrink a small sample toward the market, then measure its deviation from the market.
        results.append([(c["over"] - row.mid * (c["over"] + c["under"])) /
                        (PRIOR_GAMES + c["over"] + c["under"]) for c in (counts[k] for k in WINDOWS)])
    return np.array(results)


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 0.001, 0.999)
    return np.log(p / (1 - p))


def fit_predict(features: np.ndarray, outcomes: np.ndarray, train: np.ndarray) -> np.ndarray:
    return LogisticRegression(C=1.0, max_iter=1000).fit(
        features[train], outcomes[train]).predict_proba(features[~train])[:, 1]


def scores(frame: pd.DataFrame, train: np.ndarray, history: np.ndarray) -> pd.DataFrame:
    y = frame["hit"].to_numpy()
    market = frame["mid"].to_numpy()
    holdout = frame.loc[~train].reset_index(drop=True)
    actual = y[~train]
    rows = []
    rng = np.random.default_rng(archive.SEED)

    def record(label: str, p: np.ndarray, baseline: np.ndarray | None = None) -> None:
        row = {"prediction": label, "brier": archive.brier(p, actual), "log_loss": log_loss(actual, p)}
        if baseline is not None:
            diff = (p - actual) ** 2 - (baseline - actual) ** 2
            point, low, high = archive.interval(holdout, lambda ids: float(diff[ids].mean()), rng)
            row.update(delta_brier=point, ci_low=low, ci_high=high)
        rows.append(row)

    record("Kalshi midpoint", market[~train])
    for name in ("Simple", "Smarter"):
        model = frame[f"p_{name}"].to_numpy()
        blend = archive.WEIGHT * model + (1 - archive.WEIGHT) * market
        base = logit(np.column_stack([market, model]))
        calibrated = fit_predict(base, y, train)
        with_history = fit_predict(np.column_stack([base, history]), y, train)
        record(f"{name} fixed model/market blend", blend[~train])
        record(f"{name} fitted model/market", calibrated)
        record(f"{name} fitted model/market + consistency", with_history, calibrated)
    return pd.DataFrame(rows)


def main() -> None:
    markets, counts = archive.load_markets()
    projected, curves = archive.projections()
    frame = archive.join(markets, projected, curves, counts)
    games = pd.concat([pd.read_csv(nba_stats.NBA_DIR / f"games_{season}.csv")
                       for season in ("2024-25", "2025-26")], ignore_index=True)
    nights = sorted(frame["game_date"].unique())
    split = nights[len(nights) // 2]
    train = frame["game_date"].lt(split).to_numpy()
    print(f"Train: {nights[0]} through {nights[len(nights) // 2 - 1]}, {train.sum()} quotes.")
    print(f"Test: {split} through {nights[-1]}, {(~train).sum()} quotes, "
          f"{frame.loc[~train, 'game_date'].nunique()} nights.")
    print(scores(frame, train, history_features(frame, games)).to_string(
        index=False, float_format=lambda n: f"{n:.6f}", na_rep=""))


if __name__ == "__main__":
    main()
