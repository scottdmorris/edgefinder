"""Rolling-average baselines for NBA player stats.

These are the bar any learned model has to clear. Every prediction for a
game uses only games played strictly before it, so a baseline score is
an honest out-of-sample number.

Four baselines:
- season-to-date mean (undefined for a player's first game of a season)
- shrunk mean: season-to-date blended toward last season's per-game
  average, which fixes the early-season problem of tiny samples
- last-N mean (spans seasons, so it has no cold start)
- exponentially weighted mean (recent games count more)
"""

import pandas as pd

DEFAULT_SHRINK_GAMES = 10   # games' worth of weight given to the prior
DEFAULT_MIN_PRIOR_GAMES = 20
DEFAULT_RECENT_WINDOW = 10
DEFAULT_MIN_RECENT = 3
DEFAULT_EWM_ALPHA = 0.15


def add_baseline_predictions(
    games: pd.DataFrame,
    stat: str,
    *,
    shrink_games: int = DEFAULT_SHRINK_GAMES,
    min_prior_games: int = DEFAULT_MIN_PRIOR_GAMES,
    recent_window: int = DEFAULT_RECENT_WINDOW,
    min_recent: int = DEFAULT_MIN_RECENT,
    ewm_alpha: float = DEFAULT_EWM_ALPHA,
) -> pd.DataFrame:
    """Return a copy of `games` with one prediction column per baseline.

    `games` needs player_id, season, game_date, minutes and the stat
    column, and may span several seasons (earlier seasons supply the
    priors). Adds: n_prior, prior_minutes, pred_season_to_date,
    pred_shrunk, pred_last10, pred_ewma.
    """
    # a player never has two games on one date, so date alone orders them
    ordered = games.sort_values(["player_id", "game_date"], kind="stable")
    ordered = ordered.reset_index(drop=True)
    ordered = _attach_priors(ordered, stat, min_prior_games)

    by_season = ordered.groupby(["player_id", "season"])[stat]
    games_before = by_season.cumcount()
    sum_before = by_season.cumsum() - ordered[stat]

    by_player = ordered.groupby("player_id")[stat]
    # shifting first is what keeps a game's own result out of its prediction
    prior_games_series = by_player.transform(lambda s: s.shift(1))

    return ordered.assign(
        n_prior=games_before,
        pred_season_to_date=sum_before / games_before.where(games_before > 0),
        pred_shrunk=(sum_before + shrink_games * ordered["prior_mean"])
        / (games_before + shrink_games),
        pred_last10=prior_games_series.groupby(ordered["player_id"]).transform(
            lambda s: s.rolling(recent_window, min_periods=min_recent).mean()),
        pred_ewma=prior_games_series.groupby(ordered["player_id"]).transform(
            lambda s: s.ewm(alpha=ewm_alpha, adjust=True, ignore_na=False).mean()),
    ).drop(columns=["prior_mean", "prior_games", "prev_season", "league_prior"])


def predict_upcoming(
    games: pd.DataFrame,
    stat: str,
    player_ids,
    season: str,
    game_date,
    **options,
) -> pd.DataFrame:
    """Baseline predictions for each player's NEXT game, which hasn't
    been played yet.

    A placeholder row stands in for that game. Because a game's own
    result never feeds its own prediction, the placeholder's stat value
    is irrelevant, so no leakage is possible.
    """
    placeholders = pd.DataFrame({
        "player_id": list(player_ids),
        "season": season,
        "game_date": pd.Timestamp(game_date),
        stat: 0.0,
        "minutes": float("nan"),
        "_upcoming": True,
    })
    combined = pd.concat([games.assign(_upcoming=False), placeholders], ignore_index=True)
    predicted = add_baseline_predictions(combined, stat, **options)
    columns = ["player_id", "n_prior", "pred_season_to_date",
               "pred_shrunk", "pred_last10", "pred_ewma"]
    return predicted.loc[predicted["_upcoming"], columns].reset_index(drop=True)


def _attach_priors(games: pd.DataFrame, stat: str, min_prior_games: int) -> pd.DataFrame:
    """Add each row's prior: the player's previous-season per-game mean,
    or the previous season's league mean when they played too little."""
    seasons = sorted(games["season"].unique())
    previous_of = dict(zip(seasons[1:], seasons[:-1]))

    per_player = (
        games.groupby(["season", "player_id"])
        .agg(prior_mean=(stat, "mean"), prior_games=(stat, "count"),
             prior_minutes=("minutes", "mean"))
        .reset_index()
        .rename(columns={"season": "prev_season"})
    )
    league_mean = games.groupby("season")[stat].mean()

    # object dtype: with one season in the data every value is NaN, and a
    # float column can't merge against the string season keys
    framed = games.assign(prev_season=games["season"].map(previous_of).astype(object))
    framed = framed.merge(per_player, on=["prev_season", "player_id"], how="left")
    framed["league_prior"] = framed["prev_season"].map(league_mean)
    enough = framed["prior_games"] >= min_prior_games
    framed["prior_mean"] = framed["prior_mean"].where(enough, framed["league_prior"])
    # prior_minutes only describes players who actually had a prior season
    framed["prior_minutes"] = framed["prior_minutes"].where(enough)
    return framed
