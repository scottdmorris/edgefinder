"""Live entry point for the learned minutes model (ledger version minutes-v1).

Recipe behind the version name: the default MinutesModel trained on the
current season so far plus the two before it, projecting points as
predicted minutes times recent scoring rate. It is retrained on each run
from games finished before tonight, so it never sees the games it is
about to price.

Everything the model needs about tonight is known in advance except the
home flag, which differs per game, so one "slate" of features is built per
night and the flag is set when a particular game is projected.
"""

import numpy as np
import pandas as pd

from ..data import nba_players, nba_snapshot_plan, nba_stats
from . import nba_features, nba_minutes

MODEL_VERSION = "minutes-v1"
# Negative-binomial dispersion measured out of sample on 2025-26 by
# scripts/nba_minutes_eval.py (the points model, not the minutes alone)
MODEL_DISPERSION = 7.85
TRAIN_SEASONS = 3


def train(games: pd.DataFrame, season: str) -> nba_minutes.MinutesModel:
    """Fit on the last TRAIN_SEASONS seasons ending at `season`. `games`
    should reach back one season further so the oldest rows have priors."""
    start_year = int(season[:4])
    wanted = [nba_stats.season_label(start_year - back) for back in range(TRAIN_SEASONS)]
    features = nba_features.build_features(games)
    return nba_minutes.MinutesModel().fit(features[features["season"].isin(wanted)])


def build_slate_features(games: pd.DataFrame, season: str, game_date: str,
                         extra_features=None) -> pd.DataFrame:
    """One row of pre-game features for every player who has played this
    season, as of `game_date`. A placeholder row stands in for the game;
    since a game's own result never feeds its own features, its dummy
    values change nothing."""
    latest = (games[games["season"] == season]
              .sort_values("game_date").groupby("player_id").tail(1))
    placeholders = pd.DataFrame({
        "player_id": latest["player_id"].to_numpy(),
        "player_name": latest["player_name"].to_numpy(),
        "team": latest["team"].to_numpy(),
        "game_id": ["upcoming-" + team for team in latest["team"]],
        "game_date": pd.Timestamp(game_date),
        "season": season,
        "minutes": 0.0,
        "pts": 0.0,
        "is_home": False,
        "_upcoming": True,
    })
    combined = pd.concat([games.assign(_upcoming=False), placeholders], ignore_index=True)
    features = nba_features.build_features(combined)
    if extra_features is not None:
        features = extra_features(features)       # more inputs, built the same leak-free way
    return features[features["_upcoming"]].drop(columns="_upcoming").reset_index(drop=True)


def project_event(
    event: dict,
    player_names: list[str],
    slate_features: pd.DataFrame,
    model: nba_minutes.MinutesModel,
) -> dict[str, dict]:
    """Projected points per listed player, keyed by the odds-feed name, in
    the same shape as nba_points.project_event. Players who can't be
    matched to the two teams, or who have no scoring history, are left out."""
    home = nba_players.team_abbreviation(event["home"])
    abbreviations = {abbr for abbr in (home, nba_players.team_abbreviation(event["away"]))
                     if abbr is not None}
    matched = nba_players.match_players(player_names, slate_features, abbreviations)
    if not matched:
        return {}
    rows = slate_features[slate_features["player_id"].isin(set(matched.values()))].copy()
    rows["is_home"] = (rows["team"] == home).astype(float)
    points = nba_minutes.project_points(rows, model.predict(rows))
    by_player = dict(zip(rows["player_id"], points))
    return {
        name: {"player_id": player_id, "mean": float(by_player[player_id])}
        for name, player_id in matched.items()
        if player_id in by_player and np.isfinite(by_player[player_id])
    }


class LiveProjector:
    """Projects games with the minutes model, training it on first use.

    Callable as projector(event, player_names), so it plugs into the
    ledger recorder. One slate of features is built per game date and
    reused for every game that night. If training fails, the failure is
    remembered and re-raised for later games instead of retrying a slow
    fit for each one."""

    def __init__(self, games: pd.DataFrame, season: str):
        self._games = games
        self._season = season
        self._model: nba_minutes.MinutesModel | None = None
        self._slates: dict[str, pd.DataFrame] = {}
        self._error: Exception | None = None

    def __call__(self, event: dict, player_names: list[str]) -> dict[str, dict]:
        if self._error is not None:
            raise self._error
        game_date = nba_snapshot_plan.tip_date(event)
        try:
            if self._model is None:
                self._model = train(self._games, self._season)
            if game_date not in self._slates:
                self._slates[game_date] = build_slate_features(
                    self._games, self._season, game_date)
        except Exception as exc:
            self._error = exc
            raise
        return project_event(event, player_names, self._slates[game_date], self._model)
