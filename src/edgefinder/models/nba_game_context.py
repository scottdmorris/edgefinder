"""The game a player is about to play in: who should win, by how much, and how many
points it should produce.

A sportsbook answers this with a spread and a total. There is no archive of those
for past seasons here, so the same three numbers are worked out from the box
scores, only from games played BEFORE the one being projected:

  exp_team_pts   the player's team's expected points: what it has been scoring,
                 adjusted for what tonight's opponent has been allowing
  exp_margin     expected points for minus expected points against. A big number
                 either way is a likely blowout, which cuts starters' minutes
  exp_total      both teams' expected points together

Measured by scripts/nba_game_context_eval.py: these numbers did NOT improve the points
model (see the changelog), so no live model uses them. Kept so the test can be rerun.
"""

import numpy as np
import pandas as pd

from . import nba_context

HOME_EDGE = 2.0           # points a home team is worth over a neutral floor
FORM_WINDOW = 10          # team games behind each team's scoring and defense
MIN_FORM_GAMES = nba_context.MIN_FORM_GAMES

GAME_COLUMNS = ["exp_team_pts", "exp_margin", "exp_total"]


def _expected(scored, allowed, opp_scored, opp_allowed, league, is_home) -> dict:
    """The three numbers from each side's recent scoring and defense."""
    edge = np.where(is_home, HOME_EDGE / 2, -HOME_EDGE / 2)
    own = scored + opp_allowed - league + edge
    other = opp_scored + allowed - league - edge
    return {"exp_team_pts": own, "exp_margin": own - other, "exp_total": own + other}


def game_table(games: pd.DataFrame, window: int = FORM_WINDOW) -> pd.DataFrame:
    """One row per team per game with GAME_COLUMNS, each from games before it."""
    table = nba_context.team_games(games)
    home = games.groupby(["team", "game_id"])["is_home"].first().rename("is_home").reset_index()
    table = table.merge(home, on=["team", "game_id"], how="left")
    by_team = table.groupby("team")

    def before(column: str) -> pd.Series:
        return by_team[column].transform(
            lambda s: s.shift(1).rolling(window, min_periods=MIN_FORM_GAMES).mean())

    form = table.assign(scored=before("pts"), allowed=before("pts_against"))
    form = form.merge(nba_context.league_means(table)[["league_pf"]],
                      left_on="game_date", right_index=True, how="left")
    theirs = form[["team", "game_id", "scored", "allowed"]].rename(
        columns={"team": "opponent", "scored": "opp_scored", "allowed": "opp_allowed"})
    both = form.merge(theirs, on=["opponent", "game_id"], how="left")
    numbers = _expected(both["scored"], both["allowed"], both["opp_scored"], both["opp_allowed"],
                        both["league_pf"], both["is_home"].astype(bool))
    return both[["team", "game_id"]].assign(**numbers)


def add_game_context(features: pd.DataFrame, games: pd.DataFrame,
                     window: int = FORM_WINDOW) -> pd.DataFrame:
    """`features` with GAME_COLUMNS added. Row order and count are unchanged."""
    return features.merge(game_table(games, window), on=["team", "game_id"], how="left")

