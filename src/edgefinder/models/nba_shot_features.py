"""How a player scores, not just how much: shot habits and steadiness.

Attempts are steadier than points, so how often a player shoots and gets to the
line (per minute, smoothed) tells a model more about tonight than his last few
scores do. Everything here is worked out only from games BEFORE the one being
predicted, like the other features.
"""

import pandas as pd

SHOT_ALPHAS = {"ewma_10": 0.10, "ewma_30": 0.30}
SHOT_COLUMNS = ["fga_rate_ewma_10", "fga_rate_ewma_30", "fta_rate_ewma_10",
                "fta_rate_ewma_30", "pts_std10", "pts_season_rate"]
STEADINESS_GAMES = 10
STEADINESS_MIN_GAMES = 3


def add_shot_features(features: pd.DataFrame) -> pd.DataFrame:
    """`features` (games with the usual columns, plus fga and fta) with SHOT_COLUMNS
    added: shots and free throws per minute (smoothed at two speeds), how much his
    scoring has varied over his last games, and this season's points per minute so far.
    Rows come back sorted by player and date."""
    df = features.sort_values(["player_id", "game_date"], kind="stable").reset_index(drop=True)
    by_player = df["player_id"]

    def previous_ewm(series: pd.Series, alpha: float) -> pd.Series:
        shifted = series.groupby(by_player).shift(1)
        return shifted.groupby(by_player).transform(lambda s: s.ewm(alpha=alpha).mean())

    minutes = df["minutes"].where(df["minutes"] > 0)
    for name, alpha in SHOT_ALPHAS.items():
        for stat in ("fga", "fta"):
            df[f"{stat}_rate_{name}"] = previous_ewm(df[stat] / minutes, alpha)
    previous_points = df.groupby("player_id")["pts"].shift(1)
    df["pts_std10"] = previous_points.groupby(by_player).transform(
        lambda s: s.rolling(STEADINESS_GAMES, min_periods=STEADINESS_MIN_GAMES).std())
    season = df.groupby(["player_id", "season"])
    games_before = season.cumcount()
    minutes_before = season["minutes"].cumsum() - df["minutes"]
    df["pts_season_rate"] = ((season["pts"].cumsum() - df["pts"])
                             / minutes_before.where((games_before > 0) & (minutes_before > 0)))
    return df
