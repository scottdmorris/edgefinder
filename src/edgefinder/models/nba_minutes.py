"""Learned minutes model, and points as projected minutes times scoring rate.

Scoring splits cleanly into how long a player is on the floor and how fast
they score while there. The rate is stable; the minutes are where role
changes, rest and returns from injury show up, so that is the part worth
learning. Features come from nba_features (all known before tip-off).
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

MAX_MINUTES = 48.0
MINUTES_FEATURES = [
    "min_ewma_fast", "min_ewma_mid", "min_ewma_slow", "min_last1", "min_last3",
    "min_std10", "min_season_mean", "n_prior_season", "prior_minutes",
    "rest_days", "is_b2b", "games_last_7d", "is_home", "missed_last10",
]
HISTORY_COLUMN = "min_ewma_mid"   # rows with no minutes history can't be modeled
RATE_COLUMN = "rate_ewma_05"
DEFAULT_PARAMS = {
    "max_iter": 200, "learning_rate": 0.05, "max_depth": 4,
    "min_samples_leaf": 50, "l2_regularization": 1.0, "random_state": 0,
}


class MinutesModel:
    """Gradient-boosted minutes predictor. Handles missing features
    natively, and keeps predictions inside a real game (0-48 minutes)."""

    def __init__(self, **params):
        self.params = {**DEFAULT_PARAMS, **params}
        self._model: HistGradientBoostingRegressor | None = None
        self._columns: list[str] = []
        self.n_train = 0

    def fit(self, features: pd.DataFrame) -> "MinutesModel":
        usable = features[features[HISTORY_COLUMN].notna()]
        # scikit-learn refuses a feature that is missing in every training
        # row, which really happens: prior_minutes is empty for all of a
        # dataset's earliest season. Such a feature is ignored.
        self._columns = [c for c in MINUTES_FEATURES if usable[c].notna().any()]
        self._model = HistGradientBoostingRegressor(**self.params).fit(
            usable[self._columns], usable["minutes"])
        self.n_train = len(usable)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("fit the model before predicting")
        return np.clip(self._model.predict(features[self._columns]), 0.0, MAX_MINUTES)


def project_points(features: pd.DataFrame, minutes: np.ndarray,
                   rate_column: str = RATE_COLUMN) -> np.ndarray:
    """Expected points: projected minutes times the player's recent
    points per minute."""
    return np.asarray(minutes) * features[rate_column].to_numpy()
