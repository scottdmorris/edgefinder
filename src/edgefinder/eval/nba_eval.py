"""Scoring for NBA stat predictions.

A prediction is a mean; its spread comes from a negative binomial whose
dispersion is fitted from that method's own residuals (one parameter, so
the in-sample fit is negligible, and it keeps comparisons between
methods fair). Metrics:

- MAE / RMSE / bias: accuracy of the mean
- log_score: average log-probability the predicted distribution gave the
  real outcome (higher is better; rewards honest uncertainty)
- cov50 / cov80: how often the real outcome landed inside the central
  50% / 80% interval (a calibrated model sits near 0.50 / 0.80, a bit
  above for count data because the intervals are discrete)
"""

import numpy as np
import pandas as pd

from ..betting import negbin

DEFAULT_EDGES = (0, 5, 15, 30, 10_000)
DEFAULT_MIN_PRIOR_MINUTES = 20.0


def score_predictions(frame: pd.DataFrame, pred_col: str, stat: str) -> dict[str, float]:
    valid = frame.dropna(subset=[pred_col, stat])
    predicted = valid[pred_col].to_numpy(dtype=float)
    actual = valid[stat].to_numpy(dtype=float)
    errors = predicted - actual
    dispersion = negbin.estimate_dispersion(predicted, actual)
    low50, high50 = negbin.central_interval(predicted, dispersion, 0.5)
    low80, high80 = negbin.central_interval(predicted, dispersion, 0.8)
    return {
        "n": int(len(valid)),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "bias": float(np.mean(errors)),
        "dispersion": float(dispersion),
        "log_score": float(np.mean(negbin.logpmf(np.rint(actual), predicted, dispersion))),
        "cov50": float(np.mean((actual >= low50) & (actual <= high50))),
        "cov80": float(np.mean((actual >= low80) & (actual <= high80))),
    }


def compare_methods(frame: pd.DataFrame, pred_cols: list[str], stat: str) -> pd.DataFrame:
    """One row per method, one column per metric."""
    rows = {col: score_predictions(frame, col, stat) for col in pred_cols}
    return pd.DataFrame(rows).T


def score_by_games_played(
    frame: pd.DataFrame,
    pred_cols: list[str],
    stat: str,
    edges: tuple[int, ...] = DEFAULT_EDGES,
) -> pd.DataFrame:
    """MAE per method, split by how many games the player had already
    played this season. Shows where shrinkage and rolling windows help."""
    labels = [
        f"{lo}+ games" if hi >= 10_000 else f"{lo}-{hi - 1} games"
        for lo, hi in zip(edges[:-1], edges[1:])
    ]
    buckets = pd.cut(frame["n_prior"], bins=list(edges), right=False, labels=labels)
    table = {}
    for col in pred_cols:
        valid = frame.dropna(subset=[col, stat])
        errors = (valid[col] - valid[stat]).abs()
        table[col] = errors.groupby(buckets.loc[valid.index], observed=False).mean()
    return pd.DataFrame(table).reindex(labels)


def rotation_players(
    frame: pd.DataFrame, min_prior_minutes: float = DEFAULT_MIN_PRIOR_MINUTES
) -> pd.DataFrame:
    """Keep players who averaged real minutes LAST season. Using prior
    minutes, not this season's, avoids picking players by an outcome."""
    return frame[frame["prior_minutes"] >= min_prior_minutes]
