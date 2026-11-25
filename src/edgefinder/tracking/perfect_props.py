"""Perfect props: lines a player has cleared in every game he has played this season.

They are easy to find and almost always heavy favourites, so the price matters more than the
streak: a -1000 leg pays $1 on $10 and is priced by a book that sees the same streak. Shown
with its price and, for a finished day, how many of them hit. Display only, never in the record.
"""

import pandas as pd

from ..models import nba_stat_model
from .nba_alt import bettable

MIN_GAMES = 8           # fewer games than this is not a streak worth showing


def find(table: pd.DataFrame, games: pd.DataFrame, game_date: str,
         min_games: int = MIN_GAMES) -> list[dict]:
    """Each player's hardest "over" line on the board that he has cleared in every game this
    season before `game_date`, best price first. `table` is a board's candidate legs."""
    if table.empty or games.empty:
        return []
    before = games[games["game_date"] < pd.Timestamp(game_date)]
    if before.empty:
        return []
    season = before.loc[before["game_date"].idxmax(), "season"]
    this_season = before[before["season"] == season]
    by_player = {int(pid): rows for pid, rows in this_season.groupby("player_id")}
    found: dict[tuple[int, str], dict] = {}
    for index, row in table.iterrows():
        side = str(row["Side"])
        if side != "Over" and not (side.endswith("+") and bettable(int(side[:-1]))):
            continue
        played = by_player.get(int(row["player_id"]))
        if played is None or len(played) < min_games:
            continue
        values = played[nba_stat_model.STATS[row["stat_key"]].column]
        line = float(row["line"])
        if not (values > line).all():
            continue
        key = (int(row["player_id"]), row["stat_key"])
        better = key not in found or line > found[key]["line"] or (
            line == found[key]["line"] and int(row["Odds"]) > found[key]["odds"])   # same line, better price
        if better:
            found[key] = {"leg_id": int(index), "player": row["Player"],
                          "player_id": int(row["player_id"]), "game": row["Game"],
                          "event_id": str(row["event_id"]), "stat": row["stat_key"],
                          "bet": row["Leg"].split(" · ", 1)[-1], "side": side, "line": line,
                          "odds": int(row["Odds"]), "games": int(len(values)),
                          "book": row.get("book", ""),
                          "low": float(values.min())}
    return sorted(found.values(), key=lambda p: (-p["odds"], p["player"]))


def grade(props: list[dict], games: pd.DataFrame, game_date: str) -> list[dict]:
    """Each prop with what happened on `game_date`: hit, miss, or None when he has no box score."""
    day = games[games["game_date"] == pd.Timestamp(game_date)]
    box = {int(row["player_id"]): row for _, row in day.iterrows()}
    graded = []
    for prop in props:
        row = box.get(prop["player_id"])
        actual = None if row is None else float(row[nba_stat_model.STATS[prop["stat"]].column])
        hit = None if actual is None or pd.isna(actual) else actual > prop["line"]
        graded.append({**prop, "actual": actual, "hit": hit})
    return graded
