"""What a player's own history can't tell the model: who else is out, and who
the opponent is.

Two groups of numbers, both worked out only from games played BEFORE the one
being projected:

Absences. A team's recent roster is everyone who played in its last
ROSTER_WINDOW games. The ones who aren't in tonight's game, and who normally
play real minutes, are "lost": their typical minutes and points go
missing, and someone has to cover them. In training, "not in tonight's game"
is read from the box score. Live, it comes from the injury report, using the
same roster and the same definition, so the two match.

Opponent and pace. Each team's recent points scored, points allowed and
possessions per game, relative to the league's, say how weak the defense
across from a player is and how fast the game is likely to run.
"""

import collections

import numpy as np
import pandas as pd

ROSTER_WINDOW = 10        # team games that define the "recent roster"
ABSENT_MIN_FLOOR = 15.0   # typical minutes below this: not a loss worth counting
STARTER_MINUTES = 28.0
EWM_ALPHA = 0.2           # how fast a player's typical minutes and points update
FORM_WINDOW = 10          # team games behind the opponent and pace numbers
MIN_FORM_GAMES = 3
POSSESSION_FT = 0.44      # the usual possessions estimate: fga + 0.44 fta + turnovers

ABSENCE_COLUMNS = ["lost_min", "lost_pts", "lost_starters", "n_absent"]
OPPONENT_COLUMNS = ["opp_def_rel", "pace_rel"]
CONTEXT_COLUMNS = ABSENCE_COLUMNS + OPPONENT_COLUMNS


# ---- absences ---------------------------------------------------------------------

def _typical(state: dict, player_id: int) -> tuple[float, float] | None:
    return state.get(player_id)


def _lost(state: dict, absent: list[int]) -> dict[str, float]:
    """The cost of a set of absent players, from their typical minutes and points.
    Players who normally play fewer than ABSENT_MIN_FLOOR minutes don't count."""
    counted = [state[p] for p in absent if p in state and state[p][0] >= ABSENT_MIN_FLOOR]
    return {
        "lost_min": float(sum(minutes for minutes, _ in counted)),
        "lost_pts": float(sum(points for _, points in counted)),
        "lost_starters": float(sum(minutes >= STARTER_MINUTES for minutes, _ in counted)),
        "n_absent": float(len(counted)),
    }


def _replay(games: pd.DataFrame):
    """Walk the games in date order. Returns the absence numbers for every team
    game, and the final state: each player's typical (minutes, points) and each
    team's recent rosters. Everything used for a game was known before its date."""
    state: dict[int, tuple[float, float]] = {}
    recent: dict[str, collections.deque] = collections.defaultdict(
        lambda: collections.deque(maxlen=ROSTER_WINDOW))
    rows = []
    for _, day in games.sort_values(["game_date", "game_id"]).groupby("game_date", sort=True):
        updates = []
        for (team, game_id), box in day.groupby(["team", "game_id"]):
            present = set(box["player_id"])
            roster = set().union(*recent[team]) if recent[team] else set()
            absent = sorted(roster - present)
            rows.append({"team": team, "game_id": game_id} | _lost(state, absent))
            updates.append((team, present, box))
        # a player's own game updates his typical numbers only after the day is done
        for team, present, box in updates:
            recent[team].append(present)
            for player_id, minutes, points in zip(box["player_id"], box["minutes"], box["pts"]):
                if pd.isna(minutes):
                    continue
                old = state.get(int(player_id))
                state[int(player_id)] = (
                    (float(minutes), float(points)) if old is None else
                    (EWM_ALPHA * minutes + (1 - EWM_ALPHA) * old[0],
                     EWM_ALPHA * points + (1 - EWM_ALPHA) * old[1]))
    return pd.DataFrame(rows, columns=["team", "game_id", *ABSENCE_COLUMNS]), state, recent


def absence_table(games: pd.DataFrame) -> pd.DataFrame:
    """Minutes and points missing from each team in each game, from the box scores."""
    return _replay(games)[0]


# ---- opponent and pace ------------------------------------------------------------

def team_games(games: pd.DataFrame) -> pd.DataFrame:
    """One row per team per game: points scored and allowed, and possessions."""
    played = games.assign(poss=games["fga"] + POSSESSION_FT * games["fta"] + games["tov"])
    table = played.groupby(["team", "game_id"]).agg(
        game_date=("game_date", "first"), season=("season", "first"),
        opponent=("opponent", "first"), pts=("pts", "sum"), poss=("poss", "sum")).reset_index()
    allowed = table[["game_id", "team", "pts"]].rename(
        columns={"team": "opponent", "pts": "pts_against"})
    table = table.merge(allowed, on=["game_id", "opponent"], how="left")
    return table.sort_values(["team", "game_date", "game_id"]).reset_index(drop=True)


def team_form(table: pd.DataFrame) -> pd.DataFrame:
    """Each team's last FORM_WINDOW games' averages, as they stood BEFORE each
    game: the game's own result is never in its own form."""
    form = table.copy()
    by_team = form.groupby("team")
    for column, name in (("pts", "pf10"), ("pts_against", "pa10"), ("poss", "pace10")):
        form[name] = by_team[column].transform(
            lambda s: s.shift(1).rolling(FORM_WINDOW, min_periods=MIN_FORM_GAMES).mean())
    return form


def league_means(table: pd.DataFrame) -> pd.DataFrame:
    """League-wide points and possessions per team game before each date."""
    daily = table.groupby("game_date").agg(
        pts=("pts", "sum"), poss=("poss", "sum"), n=("pts", "size")).sort_index()
    before = daily.cumsum().shift(1)
    return pd.DataFrame({"league_pf": before["pts"] / before["n"],
                         "league_pace": before["poss"] / before["n"]})


def add_context(features: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """`features` (from nba_features.build_features) with the absence and
    opponent/pace columns added. Row order and count are unchanged."""
    table = team_games(games)
    form = team_form(table)
    own = form[["team", "game_id", "pace10"]].rename(columns={"pace10": "team_pace10"})
    opposing = form[["team", "game_id", "pa10", "pace10"]].rename(
        columns={"team": "opponent", "pa10": "opp_pa10", "pace10": "opp_pace10"})
    merged = (features.merge(own, on=["team", "game_id"], how="left")
              .merge(opposing, on=["opponent", "game_id"], how="left")
              .merge(league_means(table), left_on="game_date", right_index=True, how="left")
              .merge(absence_table(games), on=["team", "game_id"], how="left"))
    merged["opp_def_rel"] = merged["opp_pa10"] / merged["league_pf"]
    merged["pace_rel"] = (merged["team_pace10"] + merged["opp_pace10"]) / 2 / merged["league_pace"]
    return merged.drop(columns=["team_pace10", "opp_pa10", "opp_pace10",
                                "league_pf", "league_pace"])


# ---- live: tonight's slate --------------------------------------------------------

class SlateContext:
    """The context numbers for games that haven't been played, as of one date.

    Built once per date (it replays the season so far), then asked about each
    matchup. Only games before `as_of` are used."""

    def __init__(self, games: pd.DataFrame, as_of: str):
        before = games[games["game_date"] < pd.Timestamp(as_of)]
        _, self._state, self._recent = _replay(before)
        table = team_games(before)
        league = league_means(table).dropna()
        self._league_pf = (float(table["pts"].mean()) if league.empty
                           else float(league["league_pf"].iloc[-1]))
        self._league_pace = (float(table["poss"].mean()) if league.empty
                             else float(league["league_pace"].iloc[-1]))
        self._last = {team: group.tail(FORM_WINDOW) for team, group in table.groupby("team")}

    def team(self, team: str, opponent: str, out_ids: set[int]) -> dict[str, float]:
        """`team`'s numbers for a game against `opponent`, given the players the
        injury report rules out. A player who is out but isn't on the team's
        recent roster is ignored."""
        roster = set().union(*self._recent[team]) if self._recent[team] else set()
        entry = _lost(self._state, sorted(roster & {int(p) for p in out_ids}))
        mine, theirs = self._last.get(team), self._last.get(opponent)
        if mine is not None and theirs is not None and len(mine) >= MIN_FORM_GAMES \
                and len(theirs) >= MIN_FORM_GAMES:
            entry["opp_def_rel"] = float(theirs["pts_against"].mean()) / self._league_pf
            entry["pace_rel"] = (float(mine["poss"].mean()) + float(theirs["poss"].mean())) \
                / 2 / self._league_pace
        else:
            entry["opp_def_rel"] = entry["pace_rel"] = np.nan
        return entry


def slate_context(games: pd.DataFrame, as_of: str, matchups: dict[str, str],
                  out_ids: set[int]) -> dict[str, dict[str, float]]:
    """The same numbers for each team in `matchups` (team -> its opponent)."""
    context = SlateContext(games, as_of)
    return {team: context.team(team, opponent, out_ids) for team, opponent in matchups.items()}
