"""Live entry point for the second context model (ledger version context-v2).

Three changes from context-v1, each measured out of sample by
scripts/nba_improve_eval.py (choose on 2024-25, score 2025-26 once):

1. Shot habits as extra inputs: how often the player shoots and gets to the line
   per minute, how steady his scoring has been, and his scoring rate this season.
2. A blend: the average of the direct points model (with the shot inputs) and the
   minutes-times-rate model that also knows who is out. Two views of one game.
3. Honest uncertainty: the spread of the probabilities depends on the size of the
   projection. A 6-point projection is far noisier, relative to its size, than a
   25-point one, and one fixed width priced both ends of the board wrongly.

Together: points error 5.108 -> 5.090 (real, small), and a much better log score
because the probabilities are right where the bets are: low projections ("4+ points")
and big ones. The widths below are measured on the 2025-26 out-of-sample
predictions, the way context-v1's single width was.
"""

import numpy as np
import pandas as pd

from ..betting import negbin
from ..data import nba_stats
from . import nba_context, nba_context_points, nba_features, nba_minutes, nba_shot_features

MODEL_VERSION = "context-v2"
# (projected points, negative-binomial dispersion), measured out of sample on 2025-26
SPREAD_MEANS = [5.73, 10.11, 14.22, 19.32, 25.53]
SPREAD_WIDTHS = [2.29, 4.31, 6.65, 11.10, 14.81]
MODEL_DISPERSION = negbin.varying(SPREAD_MEANS, SPREAD_WIDTHS)
DIRECT_FEATURES = nba_context_points.FEATURES + nba_shot_features.SHOT_COLUMNS
MINUTES_FEATURES = nba_minutes.MINUTES_FEATURES + nba_context.ABSENCE_COLUMNS
TRAIN_SEASONS = nba_context_points.TRAIN_SEASONS


class BlendModel:
    """The average of a direct points model and a minutes-times-rate model."""

    def __init__(self):
        self._direct = nba_context_points.PointsModel(columns=DIRECT_FEATURES)
        self._minutes = nba_minutes.MinutesModel(features=MINUTES_FEATURES)
        self.n_train = 0

    def fit(self, features: pd.DataFrame) -> "BlendModel":
        self._direct.fit(features)
        self._minutes.fit(features)
        self.n_train = self._direct.n_train
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        direct = self._direct.predict(features)
        via_minutes = np.asarray(nba_minutes.project_points(features, self._minutes.predict(features)))
        return np.clip((direct + via_minutes) / 2.0, nba_context_points.MIN_POINTS, None)


def _with_inputs(games: pd.DataFrame) -> pd.DataFrame:
    features = nba_context.add_context(nba_features.build_features(games), games)
    return nba_shot_features.add_shot_features(features)


def train(games: pd.DataFrame, season: str) -> BlendModel:
    """Fit on the last TRAIN_SEASONS seasons ending at `season`. `games` should reach
    back one season further so the oldest rows have priors."""
    start_year = int(season[:4])
    wanted = [nba_stats.season_label(start_year - back) for back in range(TRAIN_SEASONS)]
    features = _with_inputs(games)
    return BlendModel().fit(features[features["season"].isin(wanted)])


class LiveProjector(nba_context_points.LiveProjector):
    """context-v1's projector (same injury report, slate and context handling) with the
    blend model and the shot inputs."""

    def _train(self) -> BlendModel:
        return train(self._games, self._season)

    def _build_slate(self, game_date: str) -> pd.DataFrame:
        return nba_context_points.nba_minutes_points.build_slate_features(
            self._games, self._season, game_date,
            extra_features=nba_shot_features.add_shot_features)
