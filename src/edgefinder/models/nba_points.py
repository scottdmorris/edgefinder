"""The current NBA player-points model.

Right now this is the best rolling baseline from scripts/nba_baseline_eval.py
(exponentially weighted mean of recent scoring). When a better model is
built, change it here and bump MODEL_VERSION so the paper ledger keeps the
two apart.
"""

import pandas as pd

from ..data import nba_players
from . import nba_baselines

MODEL_VERSION = "ewma-v1"
MODEL_STAT = "pts"
MODEL_COLUMN = "pred_ewma"
# Negative-binomial dispersion fitted on 2025-26 residuals by
# scripts/nba_baseline_eval.py (7.8 for points)
MODEL_DISPERSION = 7.8


def project_event(
    event: dict,
    player_names: list[str],
    games: pd.DataFrame,
    season: str,
    game_date: str,
) -> dict[str, dict]:
    """Projected points for each listed player in one game, keyed by the
    name the odds feed uses.

    Left out on purpose: players who can't be matched to the two teams,
    and players with no games yet THIS season. The latter are usually
    returning from injury, where minutes are the least predictable and a
    last-season average is the most misleading."""
    abbreviations = {
        abbr for abbr in (nba_players.team_abbreviation(event["home"]),
                          nba_players.team_abbreviation(event["away"]))
        if abbr is not None
    }
    this_season = games[games["season"] == season]
    matched = nba_players.match_players(player_names, this_season, abbreviations)
    if not matched:
        return {}
    predictions = nba_baselines.predict_upcoming(
        games, MODEL_STAT, sorted(set(matched.values())), season=season, game_date=game_date)
    by_id = predictions.set_index("player_id")[MODEL_COLUMN]
    return {
        name: {"player_id": player_id, "mean": float(by_id[player_id])}
        for name, player_id in matched.items()
        if player_id in by_id.index and pd.notna(by_id[player_id])
    }
