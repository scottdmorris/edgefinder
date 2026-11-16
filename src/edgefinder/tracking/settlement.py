"""Evidence that a particular NBA game has complete player logs."""

import datetime as dt

import pandas as pd

from ..data.nba_players import team_abbreviation


def completed_games(games: pd.DataFrame) -> set[tuple[str, frozenset[str]]]:
    """Require both teams, reciprocal opponents, and a full matching minutes total.

    Player logs contain played minutes, not an explicit final-game flag. Five players
    play 48 minutes each in regulation (240 team minutes); overtime adds 25. A partial
    download or one-sided game must never establish that a missing player did not play.
    """
    required = {"game_id", "game_date", "team", "opponent", "minutes"}
    if games.empty or not required.issubset(games.columns):
        return set()
    complete = set()
    for (_, date), box in games.groupby(["game_id", "game_date"]):
        totals = box.groupby("team")["minutes"].sum(min_count=1)
        if len(totals) != 2 or totals.isna().any():
            continue
        # LeagueGameLog rounds EACH player's minutes to an integer. Allow half a
        # minute per player, rather than rejecting otherwise complete real games.
        tolerance = box.groupby("team")["minutes"].count() * .5
        periods = ((totals - 240) / 25).round()
        if (periods < 0).any() or periods.nunique() != 1:
            continue
        if ((totals - (240 + periods * 25)).abs() > tolerance).any():
            continue
        teams = frozenset(totals.index)
        if any(row.opponent not in teams or row.team == row.opponent for row in box.itertuples()):
            continue
        complete.add((pd.Timestamp(date).date().isoformat(), teams))
    return complete


def can_void(row: pd.Series, today: dt.date, complete: set) -> bool:
    """A missing player can only be voided after his own game's full logs arrive."""
    date = str(row["game_date"])
    home, away = row.get("home"), row.get("away")
    if not isinstance(home, str) or not isinstance(away, str):
        matchup = row.get("game", "")
        if not isinstance(matchup, str) or " @ " not in matchup:
            return False
        away, home = matchup.split(" @ ", 1)
    def abbreviation(name: str) -> str:
        return team_abbreviation(name) or name
    return date < today.isoformat() and (date, frozenset((abbreviation(home), abbreviation(away)))) in complete
