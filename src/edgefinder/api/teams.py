"""Teams on the Players screen: the record, how the team scores and defends against the
league, who plays, tonight's lines, who is hurt, and how teammates' numbers change when a
regular sits. Everything comes from the same game logs the models use.

The with-and-without split is the part a stats site rarely shows next to a betting line:
when a starter is ruled out tonight, it says what his teammates did in the games he missed.
"""

import datetime as dt

import pandas as pd

from ..data import nba_injuries, nba_live, nba_players, nba_stats, team_colors
from ..models import nba_context
from ..tracking import nba_paper, nba_parlay
from ..tracking.nba_player_lookup import plain_letters
from . import service

LAST_GAMES = 10
RESULTS_SENT = 10
ROTATION_MINUTES = 15.0        # a regular: this many minutes a game or more
MIN_SPLIT_GAMES = 3            # games needed on each side of a with/without split
RECENT_FORM = 5                # games behind a player's recent minutes
LINE_GAMES = 10                # games behind a line's recent hit rate
PROP_STATS = ("pts", "reb", "ast", "fg3m")
SPLIT_TEAMMATES = 5
INJURY_CACHE_SECONDS = 600
PROJECTION_MODEL = "context-v2"


# ---- league tables, from the game logs ---------------------------------------------------------

def finished(games: pd.DataFrame) -> pd.DataFrame:
    """Only games with a result. A game still being played has no win or loss yet, and its
    partial score would count as a loss and drag every average down."""
    return games[games["wl"].isin(["W", "L"])]


def team_games(games: pd.DataFrame) -> pd.DataFrame:
    """One row per team per game: score both ways, possessions both ways, home and result."""
    table = nba_context.team_games(games)
    facts = games.groupby(["team", "game_id"]).agg(is_home=("is_home", "first"), wl=("wl", "first"))
    table = table.merge(facts.reset_index(), on=["team", "game_id"], how="left")
    theirs = table[["game_id", "team", "poss"]].rename(columns={"team": "opponent", "poss": "opp_poss"})
    return table.merge(theirs, on=["game_id", "opponent"], how="left") \
        .sort_values(["team", "game_date"]).reset_index(drop=True)


def _won_lost(rows: pd.DataFrame) -> str:
    wins = int((rows["wl"] == "W").sum())
    return f"{wins}-{len(rows) - wins}"


def _streak(results: pd.Series) -> str:
    """'W3' for three straight wins, newest last in `results`."""
    if results.empty:
        return ""
    latest, count = results.iloc[-1], 0
    for result in reversed(results.tolist()):
        if result != latest:
            break
        count += 1
    return f"{latest}{count}"


def record(table: pd.DataFrame, team: str) -> dict:
    mine = table[table["team"] == team]
    wins = int((mine["wl"] == "W").sum())
    return {"wins": wins, "losses": len(mine) - wins,
            "home": _won_lost(mine[mine["is_home"].astype(bool)]),
            "away": _won_lost(mine[~mine["is_home"].astype(bool)]),
            "last10": _won_lost(mine.tail(LAST_GAMES)), "streak": _streak(mine["wl"])}


def ratings(table: pd.DataFrame) -> pd.DataFrame:
    """Per team: points for and against a game, points per 100 possessions both ways, the
    difference, and pace, each ranked across the league (1 = best; for pace, 1 = fastest)."""
    sums = table.groupby("team").agg(games=("pts", "size"), pts=("pts", "sum"),
                                     against=("pts_against", "sum"), poss=("poss", "sum"),
                                     opp_poss=("opp_poss", "sum"))
    out = pd.DataFrame({
        "games": sums["games"], "ppg": sums["pts"] / sums["games"],
        "opp_ppg": sums["against"] / sums["games"],
        "ortg": sums["pts"] / sums["poss"] * 100, "drtg": sums["against"] / sums["opp_poss"] * 100,
        "pace": (sums["poss"] + sums["opp_poss"]) / 2 / sums["games"]})
    out["net"] = out["ortg"] - out["drtg"]
    for column, best_high in (("ppg", True), ("opp_ppg", False), ("ortg", True),
                              ("drtg", False), ("net", True), ("pace", True)):
        out[f"{column}_rank"] = out[column].rank(ascending=not best_high, method="min").astype(int)
    return out


def allowed(games: pd.DataFrame) -> pd.DataFrame:
    """Per team: what its opponents' players put up against it, per game, for the prop
    stats, each ranked across the league with 1 = allows the most (the softest matchup)."""
    totals = games.groupby(["game_id", "team"])[list(PROP_STATS)].sum().reset_index()
    opponents = games.groupby(["game_id", "team"])["opponent"].first().reset_index()
    against = (totals.merge(opponents, on=["game_id", "team"]).drop(columns="team")
               .rename(columns={"opponent": "team"}))
    out = against.groupby("team")[list(PROP_STATS)].mean()
    for stat in PROP_STATS:
        out[f"{stat}_rank"] = out[stat].rank(ascending=False, method="min").astype(int)
    return out


def results(table: pd.DataFrame, team: str, count: int = RESULTS_SENT) -> list[dict]:
    mine = table[table["team"] == team].sort_values("game_date", ascending=False).head(count)
    return [{"date": pd.Timestamp(r["game_date"]).strftime("%Y-%m-%d"), "opponent": r["opponent"],
             "home": bool(r["is_home"]), "result": r["wl"],
             "score": f"{int(r['pts'])}-{int(r['pts_against'])}"} for _, r in mine.iterrows()]


# ---- players ------------------------------------------------------------------------------------

def _current_players(games: pd.DataFrame, team: str) -> pd.Series:
    latest = games.sort_values("game_date").groupby("player_id")["team"].last()
    return latest[latest == team].index


def roster(games: pd.DataFrame, team: str, injuries: list | None = None) -> list[dict]:
    """Everyone whose latest game was for the team, with his averages for it, his minutes
    over his last RECENT_FORM games, and his injury status; most total minutes first."""
    mine = games[(games["team"] == team) & games["player_id"].isin(_current_players(games, team))]
    grouped = mine.groupby("player_id").agg(
        name=("player_name", "last"), games=("game_id", "nunique"), minutes=("minutes", "mean"),
        pts=("pts", "mean"), reb=("reb", "mean"), ast=("ast", "mean"), fg3m=("fg3m", "mean"),
        total=("minutes", "sum"))
    grouped = grouped.sort_values("total", ascending=False)
    recent = (mine.sort_values("game_date").groupby("player_id").tail(RECENT_FORM)
              .groupby("player_id")["minutes"].mean())
    status = {nba_players.normalize_name(i.name): nba_injuries.label(i) for i in injuries or []}
    return [{"id": int(pid), "name": row["name"], "photo": nba_parlay.headshot_url(pid),
             "games": int(row["games"]), "last5_min": round(float(recent.get(pid, 0.0)), 1),
             "status": status.get(nba_players.normalize_name(row["name"])),
             **{k: round(float(row[k]), 1) for k in ("minutes", "pts", "reb", "ast", "fg3m")}}
            for pid, row in grouped.iterrows()]


def line_facts(games: pd.DataFrame, player_id: int, line: float, projection: float | None) -> dict:
    """How often the player scored more than `line` in his last LINE_GAMES games, and how far
    the projection sits from the line."""
    last = games[games["player_id"] == player_id].sort_values("game_date").tail(LINE_GAMES)
    return {"cleared": int((last["pts"] > line).sum()), "games": len(last),
            "edge": round(projection - line, 1) if projection is not None else None}


def with_without(games: pd.DataFrame, team: str, player_id: int) -> dict:
    """How the team's other players did in its games with `player_id` and without him, since he
    first played for the team. Teammates need MIN_SPLIT_GAMES on each side; biggest change in
    points first."""
    mine = games[games["team"] == team]
    his = mine[mine["player_id"] == player_id]
    if his.empty:
        return {"with_games": 0, "without_games": 0, "teammates": []}
    since = mine[mine["game_date"] >= his["game_date"].min()]
    played = set(his["game_id"])
    others = since[since["player_id"] != player_id].assign(with_him=lambda f: f["game_id"].isin(played))
    without_games = since.loc[~since["game_id"].isin(played), "game_id"].nunique()
    rows = []
    for pid, group in others.groupby("player_id"):
        on, off = group[group["with_him"]], group[~group["with_him"]]
        if len(on) < MIN_SPLIT_GAMES or len(off) < MIN_SPLIT_GAMES:
            continue
        rows.append({"id": int(pid), "name": group["player_name"].iloc[-1],
                     "photo": nba_parlay.headshot_url(pid), "games_with": len(on), "games_without": len(off),
                     "pts_with": round(float(on["pts"].mean()), 1),
                     "pts_without": round(float(off["pts"].mean()), 1),
                     "min_with": round(float(on["minutes"].mean()), 1),
                     "min_without": round(float(off["minutes"].mean()), 1)})
    rows.sort(key=lambda r: abs(r["pts_without"] - r["pts_with"]), reverse=True)
    return {"with_games": len(played & set(since["game_id"])), "without_games": int(without_games),
            "teammates": rows[:SPLIT_TEAMMATES]}


def _side(code: str, table: pd.DataFrame, rated: pd.DataFrame, allowed_table: pd.DataFrame) -> dict:
    mine, given = rated.loc[code], allowed_table.loc[code]
    team_record = record(table, code)
    return {"code": code, "name": _names().get(code, code), "logo": nba_live.logo_url(code),
            "color": team_colors.team_color(code),
            "record": f"{team_record['wins']}-{team_record['losses']}",
            "ppg": round(float(mine["ppg"]), 1), "opp_ppg": round(float(mine["opp_ppg"]), 1),
            **{f"{k}_rank": int(mine[f"{k}_rank"]) for k in ("ortg", "drtg", "pace", "net")},
            "allowed": {stat: {"value": round(float(given[stat]), 1), "rank": int(given[f"{stat}_rank"])}
                        for stat in PROP_STATS}}


def matchup(team: str, opponent: str, table: pd.DataFrame, rated: pd.DataFrame,
            allowed_table: pd.DataFrame) -> dict:
    """Both teams' records, ranks and what each allows, side by side; the team first."""
    return {"sides": [_side(code, table, rated, allowed_table) for code in (team, opponent)
                      if code in rated.index and code in allowed_table.index]}


# ---- names ----------------------------------------------------------------------------------------

def _names() -> dict[str, str]:
    return {team["abbreviation"]: team["full_name"] for team in nba_players._teams()}


def team_options(games: pd.DataFrame) -> list[dict]:
    """Every team in the game logs, for the search box."""
    names = _names()
    return [{"code": code, "name": names.get(code, code), "logo": nba_live.logo_url(code),
             "plain": plain_letters(names.get(code, code)).lower()}
            for code in sorted(games["team"].dropna().unique())]


# ---- what the API sends ------------------------------------------------------------------------

def _season_games() -> pd.DataFrame:
    """This season's finished games (last season's early on, before any are played)."""
    games = service.load_games()
    if games.empty:
        return games
    games = finished(games)
    season = nba_stats.current_season(dt.date.today())
    current = games[games["season"] == season]
    return current if not current.empty else games[games["season"] == games["season"].max()]


def options() -> list[dict]:
    games = _season_games()
    return team_options(games) if not games.empty else []


def _injuries(team: str) -> tuple[list[nba_injuries.Injury], bool]:
    """The team's listed injuries, and whether the report could be read."""
    try:
        listed = service.cached(("injuries",), nba_injuries.fetch_injuries, INJURY_CACHE_SECONDS)
    except nba_injuries.InjuryDataError:
        return [], False
    return [i for i in listed if i.team == team], True


def _slate(team: str) -> pd.DataFrame:
    """The team's FanDuel rows on the latest slate (empty when it isn't playing)."""
    ledger = nba_paper.scope(service.load_ledger(), book=nba_paper.DEFAULT_BOOK)
    if ledger.empty:
        return ledger
    latest = ledger[ledger["game_date"] == ledger["game_date"].max()]
    name = _names().get(team)
    return latest[(latest["home"] == name) | (latest["away"] == name)]


def not_yet_played(slate: pd.DataFrame, games: pd.DataFrame, team: str) -> pd.DataFrame:
    """The slate rows, or none once the team has a finished game on or after the slate's
    date: a game that is over is not 'next', and its lines are history."""
    if slate.empty:
        return slate
    played = games.loc[games["team"] == team, "game_date"]
    if not played.empty and played.max() >= pd.Timestamp(str(slate["game_date"].iloc[0])):
        return slate.iloc[0:0]
    return slate


def _next_game(team: str, slate: pd.DataFrame) -> dict | None:
    if slate.empty:
        return None
    first = slate.iloc[0]
    home = nba_players.team_abbreviation(str(first["home"]))
    away = nba_players.team_abbreviation(str(first["away"]))
    opponent = away if home == team else home
    if not opponent:
        return None
    return {"opponent": opponent, "home": home == team, "tip": first["commence_time"],
            "date": first["game_date"]}


def _tonight(team: str, slate: pd.DataFrame, games: pd.DataFrame) -> list[dict]:
    """The team's players with a FanDuel points line on the latest slate: the line, the
    projection of the model the app leads with, and how often he cleared it lately."""
    if slate.empty:
        return []
    rows = slate[slate["player_id"].isin(set(_current_players(service.load_games(), team)))]
    out = []
    for pid, group in rows.groupby("player_id"):
        first = group.iloc[0]
        model = group[group["model_version"] == PROJECTION_MODEL]
        projection = service._num(model["model_mean"].iloc[0], 1) if not model.empty else None
        out.append({"id": int(pid), "name": first["player"], "line": float(first["line"]),
                    "over": int(first["over_odds"]), "under": int(first["under_odds"]),
                    "projection": projection,
                    **line_facts(games, int(pid), float(first["line"]), projection)})
    return sorted(out, key=lambda r: -r["line"])


def _absences(games: pd.DataFrame, team: str, injuries: list, roster_rows: list[dict]) -> list[dict]:
    """For each regular listed as out: his status and what teammates did without him."""
    regulars = {nba_players.normalize_name(p["name"]): p for p in roster_rows
                if p["minutes"] >= ROTATION_MINUTES}
    out = []
    for injury in injuries:
        player = regulars.get(nba_players.normalize_name(injury.name))
        if player is None or not injury.is_out:
            continue
        out.append({"id": player["id"], "name": player["name"], "status": nba_injuries.label(injury),
                    "detail": injury.detail, **with_without(games, team, player["id"])})
    return out


def profile(team: str) -> dict:
    games = _season_games()
    code = team.upper()
    if games.empty or code not in set(games["team"]):
        raise service.NotFound(f"no games for team {team}")
    table = team_games(games)
    rated = ratings(table)
    allowed_table = allowed(games)
    injuries, report_ok = _injuries(code)
    roster_rows = roster(games, code, injuries)
    slate = not_yet_played(_slate(code), games, code)
    upcoming = _next_game(code, slate)
    return {
        "code": code, "name": _names().get(code, code), "season": games["season"].iloc[-1],
        "logo": nba_live.logo_url(code), "color": team_colors.team_color(code),
        "record": record(table, code), "teams_in_league": len(rated),
        "ratings": {k: (service._num(v, 1) if not k.endswith("rank") and k != "games" else int(v))
                    for k, v in rated.loc[code].items()},
        "allowed": {stat: {"value": round(float(allowed_table.loc[code, stat]), 1),
                           "rank": int(allowed_table.loc[code, f"{stat}_rank"])}
                    for stat in PROP_STATS},
        "next_game": upcoming,
        "matchup": (matchup(code, upcoming["opponent"], table, rated, allowed_table)
                    if upcoming else None),
        "results": results(table, code), "roster": roster_rows,
        "tonight": _tonight(code, slate, games),
        "injury_report": report_ok,
        "injuries": [{"name": i.name, "status": nba_injuries.label(i), "detail": i.detail}
                     for i in injuries],
        "absences": _absences(games, code, injuries, roster_rows),
    }
