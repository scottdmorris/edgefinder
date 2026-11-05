"""Live entry point for the context model (ledger version context-v1).

One gradient-boosted model predicts a player's points directly from his own
history (minutes trend, rest, scoring rate) plus the context the other models
can't see: how many rotation minutes and points are missing from his team
tonight, how weak the opposing defense is, and how fast the game is likely to
run. It is retrained on each run from games finished before tonight.

Tonight's absences come from the injury report. Training reads the same
quantity from past box scores, with the same roster and the same definition,
so the two match. If the injury report can't be fetched the model carries on
as if nobody were out, which makes it no worse informed than the others.

Measured out of sample on 2025-26 by scripts/nba_context_eval.py: points error
5.137 -> 5.108 against minutes-v1, a small gain that is statistically real.
"""

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from ..data import nba_injuries, nba_players, nba_snapshot_plan, nba_stats
from . import nba_context, nba_features, nba_minutes, nba_minutes_points

log = logging.getLogger(__name__)

MODEL_VERSION = "context-v1"
# Negative-binomial dispersion measured on the 2025-26 out-of-sample predictions
MODEL_DISPERSION = 8.2
TRAIN_SEASONS = 3
RATE_COLUMNS = ["rate_ewma_05", "rate_ewma_10"]
FEATURES = nba_minutes.MINUTES_FEATURES + RATE_COLUMNS + nba_context.CONTEXT_COLUMNS
PARAMS = {"loss": "poisson", "max_iter": 200, "learning_rate": 0.05, "max_depth": 4,
          "min_samples_leaf": 50, "l2_regularization": 1.0, "random_state": 0}
MIN_POINTS = 0.05


class PointsModel:
    """Gradient-boosted direct points predictor. Handles missing inputs natively
    and never predicts a negative score."""

    def __init__(self, **params):
        self.params = {**PARAMS, **params}
        self._model: HistGradientBoostingRegressor | None = None
        self._columns: list[str] = []
        self.n_train = 0

    def fit(self, features: pd.DataFrame) -> "PointsModel":
        usable = features[features["min_ewma_mid"].notna() & features["pts"].notna()]
        # an input that is missing in every training row can't be used
        self._columns = [c for c in FEATURES if usable[c].notna().any()]
        self._model = HistGradientBoostingRegressor(**self.params).fit(
            usable[self._columns], usable["pts"])
        self.n_train = len(usable)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("fit the model before predicting")
        return np.clip(self._model.predict(features[self._columns]), MIN_POINTS, None)


def train(games: pd.DataFrame, season: str) -> PointsModel:
    """Fit on the last TRAIN_SEASONS seasons ending at `season`. `games` should
    reach back one season further so the oldest rows have priors."""
    start_year = int(season[:4])
    wanted = [nba_stats.season_label(start_year - back) for back in range(TRAIN_SEASONS)]
    features = nba_context.add_context(nba_features.build_features(games), games)
    return PointsModel().fit(features[features["season"].isin(wanted)])


def project_event(
    event: dict,
    player_names: list[str],
    slate_features: pd.DataFrame,
    model: PointsModel,
    context: dict[str, dict[str, float]],
) -> dict[str, dict]:
    """Projected points per listed player, keyed by the odds-feed name, in the
    same shape as the other models. `context` maps each team to its numbers for
    this game. Players who can't be matched to the two teams, or who have no
    scoring history, are left out."""
    home = nba_players.team_abbreviation(event["home"])
    abbreviations = {abbr for abbr in (home, nba_players.team_abbreviation(event["away"]))
                     if abbr is not None}
    matched = nba_players.match_players(player_names, slate_features, abbreviations)
    if not matched:
        return {}
    rows = slate_features[slate_features["player_id"].isin(set(matched.values()))].copy()
    rows["is_home"] = (rows["team"] == home).astype(float)
    for column in nba_context.CONTEXT_COLUMNS:
        rows[column] = rows["team"].map(lambda team: context.get(team, {}).get(column, np.nan))
    by_player = dict(zip(rows["player_id"], model.predict(rows)))
    has_history = rows.set_index("player_id")["rate_ewma_05"].notna().to_dict()
    return {
        name: {"player_id": player_id, "mean": float(by_player[player_id])}
        for name, player_id in matched.items()
        if player_id in by_player and has_history.get(player_id)
    }


class LiveProjector:
    """Projects games with the context model, training it on first use.

    Callable as projector(event, player_names), so it plugs into the ledger
    recorder. Per game date it builds one slate of features, one context
    snapshot, and reads the injury report once. A training failure is
    remembered and re-raised rather than retried for every game; an injury
    report failure is logged and treated as nobody known to be out."""

    def __init__(self, games: pd.DataFrame, season: str, injuries=None):
        self._games = games
        self._season = season
        self._injuries = injuries
        self._model: PointsModel | None = None
        self._slates: dict[str, pd.DataFrame] = {}
        self._contexts: dict[str, nba_context.SlateContext] = {}
        self._out: set[int] | None = None
        self._error: Exception | None = None

    def _out_ids(self) -> set[int]:
        if self._out is None:
            self._out = set()
            if self._injuries is not None:
                try:
                    self._out = nba_injuries.out_player_ids(
                        self._injuries(), self._games, self._season)
                except nba_injuries.InjuryDataError as error:
                    log.warning("%s; projecting as if nobody is out", error)
        return self._out

    def __call__(self, event: dict, player_names: list[str]) -> dict[str, dict]:
        if self._error is not None:
            raise self._error
        game_date = nba_snapshot_plan.tip_date(event)
        try:
            if self._model is None:
                self._model = train(self._games, self._season)
            if game_date not in self._slates:
                self._slates[game_date] = nba_minutes_points.build_slate_features(
                    self._games, self._season, game_date)
                self._contexts[game_date] = nba_context.SlateContext(self._games, game_date)
        except Exception as exc:
            self._error = exc
            raise
        home = nba_players.team_abbreviation(event["home"])
        away = nba_players.team_abbreviation(event["away"])
        out = self._out_ids()
        context = {}
        if home and away:
            context = {home: self._contexts[game_date].team(home, away, out),
                       away: self._contexts[game_date].team(away, home, out)}
        return project_event(event, player_names, self._slates[game_date], self._model, context)
