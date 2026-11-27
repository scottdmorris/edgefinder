"""Pregame counts against a fixed player-stat line."""

import pandas as pd

from ..data import nba_stats

WINDOWS = {"last5": 5, "last10": 10, "last20": 20}


def played_games(games: pd.DataFrame, column: str) -> pd.DataFrame:
    """Keep usable appearances in chronological order, with dates normalized."""
    if games.empty:
        return pd.DataFrame(columns=["game_date", "season", column])
    dates = pd.to_datetime(games["game_date"]).dt.normalize()
    played = pd.to_numeric(games["minutes"], errors="coerce").gt(0)
    valid = played & games[column].notna() & dates.notna()
    return games.loc[valid, ["season", column]].assign(game_date=dates[valid]).sort_values("game_date")


def line_counts(history: pd.DataFrame, column: str, date: pd.Timestamp,
                line: float) -> dict[str, dict[str, int]]:
    """Count both sides on usable games strictly before the slate's game date."""
    prior = history.iloc[:history["game_date"].searchsorted(date, side="left")] if not history.empty else history
    season = nba_stats.current_season(date.date())
    windows = {key: prior[column].tail(size) for key, size in WINDOWS.items()}
    windows["season"] = prior.loc[prior["season"] == season, column]
    counts = {}
    for key, values in windows.items():
        over, under = int((values > line).sum()), int((values < line).sum())
        counts[key] = {"over": over, "under": under, "pushes": len(values) - over - under}
    return counts
