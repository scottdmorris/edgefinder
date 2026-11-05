"""Look a player up: season averages, recent games, and how often he has
cleared a number.

Works on the game logs the models already use. The hit-rate question
("how often does he score more than 24.5?") is the one people actually ask
before a bet, so it sits next to the averages.
"""

import pandas as pd

from ..data.nba_players import normalize_name

STATS = {"Points": "pts", "Rebounds": "reb", "Assists": "ast", "3-pointers": "fg3m"}
AVERAGED = ["minutes", "pts", "reb", "ast", "fg3m", "stl", "blk"]
MIN_SEASON_GAMES = 3       # before this a "season" average says little


def search(games: pd.DataFrame, query: str, limit: int = 8) -> pd.DataFrame:
    """Players whose name contains every word typed, most-played first.
    Accents, case, punctuation and suffixes like Jr. are ignored."""
    words = normalize_name(query).split()
    if not words:
        return pd.DataFrame(columns=["player_id", "player_name", "team"])
    names = games["player_name"].map(normalize_name)
    matches = games[names.map(lambda name: all(word in name for word in words))]
    if matches.empty:
        return pd.DataFrame(columns=["player_id", "player_name", "team"])
    latest = matches.sort_values("game_date").groupby("player_id").tail(1)
    played = matches.groupby("player_id")["minutes"].sum().rename("total_minutes")
    found = latest.join(played, on="player_id").sort_values("total_minutes", ascending=False)
    return found[["player_id", "player_name", "team"]].head(limit).reset_index(drop=True)


def player_games(games: pd.DataFrame, player_id: int) -> pd.DataFrame:
    return games[games["player_id"] == player_id].sort_values("game_date")


def current_season_games(history: pd.DataFrame) -> pd.DataFrame:
    """This season's games, or last season's while this one is too young to
    say anything."""
    seasons = sorted(history["season"].unique())
    this_season = history[history["season"] == seasons[-1]]
    if len(this_season) >= MIN_SEASON_GAMES or len(seasons) == 1:
        return this_season
    return history[history["season"] == seasons[-2]]


def season_averages(history: pd.DataFrame) -> dict:
    """Per-game averages over the games given, plus how many there were."""
    if history.empty:
        return {"games": 0}
    averages = {stat: float(history[stat].mean()) for stat in AVERAGED}
    return {"games": len(history), "season": history["season"].iloc[-1], **averages}


def recent_games(history: pd.DataFrame, count: int = 10) -> pd.DataFrame:
    """The last `count` games, newest first, in a form ready to show."""
    latest = history.sort_values("game_date", ascending=False).head(count)
    return pd.DataFrame({
        "Date": latest["game_date"].dt.strftime("%b %d"),
        "Opponent": [("vs " if home else "@ ") + str(opp)
                     for home, opp in zip(latest["is_home"], latest["opponent"])],
        "Result": latest["wl"].fillna("").to_numpy(),
        "Min": latest["minutes"].round().astype("Int64").to_numpy(),
        "Pts": latest["pts"].to_numpy(), "Reb": latest["reb"].to_numpy(),
        "Ast": latest["ast"].to_numpy(), "3PM": latest["fg3m"].to_numpy(),
    }).reset_index(drop=True)


def hit_rate(history: pd.DataFrame, stat: str, line: float, last: int | None = None) -> dict:
    """How often the player went over `line` in a stat (the last `last`
    games, or all given). A whole-number line that he lands on exactly is
    neither over nor under."""
    sample = history.sort_values("game_date")
    if last is not None:
        sample = sample.tail(last)
    values = sample[stat]
    over, under = int((values > line).sum()), int((values < line).sum())
    return {"games": len(values), "over": over, "under": under,
            "over_pct": over / len(values) * 100.0 if len(values) else 0.0}
