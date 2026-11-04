"""Pre-game features for NBA minutes and scoring-rate models.

Every feature for a game uses only what is known before tip-off: the
player's own earlier games, the team's schedule, and the home flag. A
game's own result never feeds its own features (the tests enforce this),
so a model trained on these has not seen the answer.

The one signal that is easy to miss is `missed_last10`: how many of the
team's last 10 games the player sat out. It flags players returning from
injury or rest, whose minutes a plain average badly overstates.
"""

import numpy as np
import pandas as pd

MIN_ALPHAS = {"min_ewma_fast": 0.5, "min_ewma_mid": 0.3, "min_ewma_slow": 0.1}
RATE_ALPHAS = {"rate_ewma_05": 0.05, "rate_ewma_10": 0.10}
MAX_REST_DAYS = 10        # an offseason gap shouldn't read as "very rested"
MISSED_WINDOW = 10        # team games looked back over
RECENT_DAYS = 7
MIN_PRIOR_SEASON_GAMES = 20

FEATURE_COLUMNS = [
    "min_ewma_fast", "min_ewma_mid", "min_ewma_slow", "min_last1", "min_last3",
    "min_std10", "min_season_mean", "n_prior_season", "prior_minutes",
    "rest_days", "is_b2b", "games_last_7d", "is_home", "missed_last10",
    "rate_ewma_05", "rate_ewma_10",
]


def build_features(games: pd.DataFrame) -> pd.DataFrame:
    """Return `games` sorted by player and date, with FEATURE_COLUMNS added.

    Needs player_id, team, game_id, game_date, season, minutes, pts and
    is_home. May span several seasons (earlier ones supply the priors).
    """
    df = games.sort_values(["player_id", "game_date"], kind="stable").reset_index(drop=True)
    by_player = df.groupby("player_id")
    previous_minutes = by_player["minutes"].shift(1)
    previous_points = by_player["pts"].shift(1)

    def over_history(series: pd.Series, func) -> pd.Series:
        return series.groupby(df["player_id"]).transform(func)

    def ewm(alpha: float):
        return lambda s: s.ewm(alpha=alpha, adjust=True, ignore_na=False).mean()

    features: dict[str, pd.Series] = {
        name: over_history(previous_minutes, ewm(alpha)) for name, alpha in MIN_ALPHAS.items()
    }
    features["min_last1"] = previous_minutes
    features["min_last3"] = over_history(previous_minutes, lambda s: s.rolling(3, min_periods=1).mean())
    features["min_std10"] = over_history(previous_minutes, lambda s: s.rolling(10, min_periods=3).std())

    in_season = df.groupby(["player_id", "season"])["minutes"]
    games_before = in_season.cumcount()
    features["n_prior_season"] = games_before
    features["min_season_mean"] = (
        (in_season.cumsum() - df["minutes"]) / games_before.where(games_before > 0))
    features["prior_minutes"] = _prior_season_minutes(df)

    rest = (df["game_date"] - by_player["game_date"].shift(1)).dt.days.clip(upper=MAX_REST_DAYS)
    features["rest_days"] = rest
    features["is_b2b"] = (rest <= 1).astype(float).where(rest.notna())
    features["games_last_7d"] = _games_in_window(df, RECENT_DAYS)
    features["is_home"] = df["is_home"].astype(float)
    features["missed_last10"] = _missed_recent_team_games(df)

    minutes_for_rate = {
        name: over_history(previous_minutes, ewm(alpha)) for name, alpha in RATE_ALPHAS.items()}
    for name, alpha in RATE_ALPHAS.items():
        points = over_history(previous_points, ewm(alpha))
        features[name] = points / minutes_for_rate[name].where(minutes_for_rate[name] > 0)
    return df.assign(**features)


def _prior_season_minutes(df: pd.DataFrame) -> pd.Series:
    seasons = sorted(df["season"].unique())
    previous_of = dict(zip(seasons[1:], seasons[:-1]))
    per_season = df.groupby(["season", "player_id"])["minutes"].agg(["mean", "count"]).reset_index()
    per_season = per_season[per_season["count"] >= MIN_PRIOR_SEASON_GAMES].rename(
        columns={"season": "prev_season", "mean": "prior_minutes"})
    keyed = df[["player_id"]].assign(prev_season=df["season"].map(previous_of).astype(object))
    merged = keyed.merge(
        per_season[["prev_season", "player_id", "prior_minutes"]],
        on=["prev_season", "player_id"], how="left")
    return pd.Series(merged["prior_minutes"].to_numpy(), index=df.index)


def _games_in_window(df: pd.DataFrame, days: int) -> pd.Series:
    """Games the player played in the `days` before each game."""
    counts = np.zeros(len(df))
    dates = df["game_date"].to_numpy().astype("datetime64[D]").astype(np.int64)
    for positions in df.groupby("player_id").indices.values():
        player_dates = dates[positions]
        counts[positions] = np.arange(len(positions)) - np.searchsorted(
            player_dates, player_dates - days, side="left")
    return pd.Series(counts, index=df.index)


def _missed_recent_team_games(df: pd.DataFrame) -> pd.Series:
    """How many of the team's previous MISSED_WINDOW games the player sat
    out. The window only starts once the player joined the team, so a
    trade doesn't count every earlier team game as missed, and a
    player's first game for a team has no history (NaN)."""
    schedule = (
        df[["team", "game_id", "game_date"]]
        .drop_duplicates(["team", "game_id"])
        .sort_values(["team", "game_date", "game_id"])
    )
    schedule = schedule.assign(team_idx=schedule.groupby("team").cumcount())
    team_idx = df[["team", "game_id"]].merge(
        schedule[["team", "game_id", "team_idx"]], on=["team", "game_id"], how="left"
    )["team_idx"].to_numpy()

    missed = np.full(len(df), np.nan)
    for positions in df.groupby(["player_id", "team"]).indices.values():
        indexes = team_idx[positions]
        appearances = np.arange(len(positions)) - np.searchsorted(
            indexes, indexes - MISSED_WINDOW, side="left")
        window = np.minimum(MISSED_WINDOW, indexes - indexes[0])
        result = (window - appearances).astype(float)
        result[0] = np.nan
        missed[positions] = result
    return pd.Series(missed, index=df.index)
