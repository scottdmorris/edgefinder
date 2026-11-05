"""The stats we project and bet on, in one place, and the rolling-average
projection that works for any of them.

Each stat knows its game-log column, the Odds API market that carries its
lines, how to word it, and its negative-binomial dispersion. Points keep
their own file (nba_points.py) for the model's version history, but they
use the same projection function as everything else.
"""

from dataclasses import dataclass

import pandas as pd

from ..data import nba_players
from . import nba_baselines

PROJECTION_COLUMN = "pred_ewma"


@dataclass(frozen=True)
class Stat:
    key: str            # what the ledger stores: "points"
    column: str         # the game-log column: "pts"
    market: str         # the Odds API market that carries its lines
    label: str          # for buttons: "Points"
    dispersion: float   # negative-binomial spread, fitted on past residuals
    live_field: str     # the PlayerLine attribute that holds it in a live box score


# Dispersions are method-of-moments fits to walk-forward residuals of the
# rolling-average projection on the 2025-26 season (players projected for
# real minutes), from scripts/nba_stat_report.py. A larger number means a
# tighter, more Poisson-like spread: rebounds and assists are steadier
# counts than points. Points keep the 7.8 fitted on the original baseline
# evaluation so existing ledger rows stay comparable.
STATS: dict[str, Stat] = {stat.key: stat for stat in (
    Stat("points", "pts", "player_points", "Points", 7.8, "points"),
    Stat("rebounds", "reb", "player_rebounds", "Rebounds", 10.7, "rebounds"),
    Stat("assists", "ast", "player_assists", "Assists", 11.3, "assists"),
    Stat("threes", "fg3m", "player_threes", "3-pointers", 6.8, "threes"),
)}
DEFAULT_STAT = "points"


def by_market(market: str) -> Stat:
    return next(stat for stat in STATS.values() if stat.market == market)


def project_event(
    stat: Stat,
    event: dict,
    player_names: list[str],
    games: pd.DataFrame,
    season: str,
    game_date: str,
) -> dict[str, dict]:
    """Projected `stat` for each listed player in one game, keyed by the name
    the odds feed uses.

    Left out on purpose: players who can't be matched to the two teams, and
    players with no games yet THIS season. The latter are usually returning
    from injury, where minutes are the least predictable and a last-season
    average is the most misleading."""
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
        games, stat.column, sorted(set(matched.values())), season=season, game_date=game_date)
    by_id = predictions.set_index("player_id")[PROJECTION_COLUMN]
    return {
        name: {"player_id": player_id, "mean": float(by_id[player_id])}
        for name, player_id in matched.items()
        if player_id in by_id.index and pd.notna(by_id[player_id])
    }
