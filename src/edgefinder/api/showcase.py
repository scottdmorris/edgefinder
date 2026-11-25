"""The game simulation and Perfect Props, shaped for the Parlay screen. Display only."""

import hashlib

import numpy as np
import pandas as pd

from ..models import nba_stat_model
from ..tracking import game_sim, nba_parlay, perfect_props, possession_sim
from . import service

TEAM_GAMES = 15          # recent games behind a team's usual scoring
RECAP_LOOKBACK = 3       # days searched back for the latest finished one
SIM_RUNS = 2000          # games played possession by possession per simulation
OREB_SHARE = 0.23        # share of a team's rebounds that are offensive, for its possessions
STAT_BOX = {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes": "threes"}


def _seed(*parts: str) -> int:
    """The same game gives the same simulation on every load."""
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


def _team_points(games: pd.DataFrame) -> dict[str, float]:
    """Each team's average points over its last TEAM_GAMES games."""
    if games.empty or "team" not in games.columns:
        return {}
    per_game = (games.groupby(["team", "game_id", "game_date"], as_index=False)["pts"].sum()
                .sort_values("game_date"))
    return {team: float(rows.tail(TEAM_GAMES)["pts"].mean()) for team, rows in per_game.groupby("team")}


def _players(rows: pd.DataFrame, teams: dict[int, str], averages: dict,
             sides: tuple[str, str]) -> list[game_sim.Player]:
    players = []
    for pid, legs in rows.groupby("player_id"):
        team = teams.get(int(pid))
        if team not in sides:
            continue                              # a late trade the logs haven't caught
        means, lines = {}, {}
        for stat, stat_legs in legs.groupby("stat_key"):
            projected = stat_legs["projection"].dropna()
            if len(projected):
                means[stat] = float(projected.iloc[0])
            lines[stat] = [float(x) for x in stat_legs["line"].unique()]
        for stat, spec in nba_stat_model.STATS.items():   # stats without a line: his average
            if stat not in means and spec.column in averages.get(int(pid), {}):
                means[stat] = averages[int(pid)][spec.column][0]
        if "points" in means:
            players.append(game_sim.Player(int(pid), legs["Player"].iloc[0], team, means, lines))
    return players


def _pace(games: pd.DataFrame, teams: tuple[str, str]) -> float:
    """The two teams' average possessions per game over their recent games."""
    if games.empty:
        return possession_sim.DEFAULT_PACE
    per_game = games.groupby(["team", "game_id", "game_date"], as_index=False)[["fga", "fta", "tov", "reb"]].sum()
    per_game["poss"] = per_game["fga"] + 0.44 * per_game["fta"] + per_game["tov"] - OREB_SHARE * per_game["reb"]
    paces = [float(rows.sort_values("game_date").tail(TEAM_GAMES)["poss"].mean())
             for team, rows in per_game.groupby("team") if team in teams]
    return float(np.mean(paces)) if paces else possession_sim.DEFAULT_PACE


def _rosters(players: list[game_sim.Player], games: pd.DataFrame, averages: dict,
             rest: dict[str, float], teams: tuple[str, str]) -> dict[str, list[possession_sim.Profile]] | None:
    rosters = {}
    for n, team in enumerate(teams):
        mine = []
        for player in (p for p in players if p.team == team):
            minutes = averages.get(player.player_id, {}).get("minutes", (None, None))[1]
            made = possession_sim.profile(player.name, player.player_id, team,
                                          games[games["player_id"] == player.player_id],
                                          minutes=minutes, points=player.means.get("points"))
            if made:
                mine.append(made)
        used = sum(p.minutes for p in mine)
        if used > possession_sim.TEAM_MINUTES:          # listed players can't play more than 240
            scale = possession_sim.TEAM_MINUTES / used
            mine = [possession_sim.replace(p, minutes=p.minutes * scale) for p in mine]
            used = possession_sim.TEAM_MINUTES
        left = possession_sim.TEAM_MINUTES - used
        if left > 1:
            count = 3 if left > 60 else 2 if left > 20 else 1
            mine += possession_sim.bench(team, left, rest.get(team, 0.0), count, first_id=-10 * (n + 1))
        if len(mine) < 5:
            return None
        rosters[team] = possession_sim.starters(mine)
    return rosters


def _possessions(players, games, averages, away, home, rest, seed) -> dict | None:
    """The game played SIM_RUNS times possession by possession: the summary the panel shows, and
    the most typical game event by event to watch. None without the logs to build players from."""
    if games.empty or not players:
        return None
    rosters = _rosters(players, games, averages, rest, (away, home))
    if rosters is None:
        return None
    targets = {team: rest.get(team, 0.0) + sum(p.means.get("points", 0.0) for p in players if p.team == team)
               for team in (away, home)}
    result = possession_sim.simulate(rosters, away, home, _pace(games, (away, home)), targets, SIM_RUNS, seed)
    scores, margin = result["scores"], result["margin"]
    home_wins = margin > 0
    lines = {p.player_id: p.lines for p in players}
    summary = []
    for team in (away, home):
        for prof in rosters[team]:
            if prof.player_id < 0:
                continue
            stats = {}
            for stat, column in STAT_BOX.items():
                values = np.array([g["box"][prof.player_id][column] for g in result["games"]], dtype=float)
                stats[stat] = {"average": round(float(values.mean()), 1),
                               "low": int(np.percentile(values, 10)), "high": int(np.percentile(values, 90)),
                               "lines": [{"line": line, "over_pct": round(100 * float((values > line).mean()), 1)}
                                         for line in sorted(set(lines.get(prof.player_id, {}).get(stat, [])))]}
            summary.append({"player_id": prof.player_id, "player": prof.name, "team": team, "stats": stats})
    watched = result["watched"]
    real = [p for team in (away, home) for p in rosters[team] if p.player_id >= 0]
    box = sorted(({"player_id": p.player_id, "player": p.name, "team": p.team,
                   **{stat: watched["box"][p.player_id][column] for stat, column in STAT_BOX.items()}}
                  for p in real), key=lambda row: -row["points"])
    bench = {team: sum(watched["box"][p.player_id]["points"] for p in rosters[team] if p.player_id < 0)
             for team in (away, home)}
    roster = [{"id": p.player_id, "name": p.name, "team": team, "starter": p.starter,
               "photo": nba_parlay.headshot_url(p.player_id) if p.player_id >= 0 else ""}
              for team in (away, home) for p in rosters[team]]
    return {
        "runs": len(result["games"]),
        "teams": {away: game_sim._team(scores[away], ~home_wins), home: game_sim._team(scores[home], home_wins)},
        "total": game_sim._spread(result["total"]),
        "margin": game_sim._spread(margin),
        "margin_chart": game_sim._margin_chart(margin),
        "players": summary,
        "typical": {"score": watched["score"], "rest": bench, "box": box},
        "watch": {"events": watched["events"], "roster": roster, "periods": watched["periods"]},
    }


def simulation(date: str | None, book: str | None, model: str | None, game: str) -> dict:
    table, chosen = service.candidates(date, book, model)
    rows = table[table["Game"] == game]
    if rows.empty:
        raise service.NotFound(f"no game {game[:80]!r} on this board")
    away, home = rows["away_abbr"].iloc[0], rows["home_abbr"].iloc[0]

    def run() -> dict:
        games, averages = service.load_games(), service._averages()
        players = _players(rows, service._teams(), averages, (away, home))
        usual = _team_points(games)
        listed = {team: sum(averages.get(p.player_id, {}).get("pts", (0.0, 0.0))[0]
                            for p in players if p.team == team) for team in (away, home)}
        rest = {team: max(usual.get(team, listed[team]) - listed[team], 0.0) for team in (away, home)}
        seed = _seed(chosen["date"], chosen["book"], chosen["model"], game)
        base = {"game": game, "away": away, "home": home, "model": chosen["model"],
                "model_short": service.model_short(chosen["model"])}
        played = _possessions(players, games, averages, away, home, rest, seed)
        if played is None:           # no game logs to build players from: the box-score version
            return {**base, **game_sim.simulate(players, away, home, rest, seed=seed), "watch": None}
        return {**base, **played}
    return service.cached(("simulation", chosen["date"], chosen["book"], chosen["model"], game), run, 300)


def _every_book(date: str, first: str | None = None, table: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every price source's legs on a day, each with its book: one book's main lines are rarely
    cleared every game, while the ladders (Kalshi, FanDuel's X+) reach the easy numbers."""
    try:
        _, chosen = service.candidates(date, first, None)
    except service.NotFound:
        return pd.DataFrame()
    tables = []
    for book in chosen["found"]:
        try:
            legs = table if (book == first and table is not None) else service.candidates(date, book, None)[0]
        except service.NotFound:
            continue
        tables.append(legs.assign(book=book))
    return pd.concat(tables) if tables else pd.DataFrame()


def perfect(date: str | None, book: str | None, model: str | None) -> dict:
    """The chosen day's perfect props, and the latest finished day's with how they did."""
    table, chosen = service.candidates(date, book, model)
    games = service.load_games()
    today = perfect_props.find(_every_book(chosen["date"], chosen["book"], table), games, chosen["date"])
    started = {e for e, tip in service._tips().items() if service._started(tip)}
    today = [{**p, "started": p["event_id"] in started} for p in today]
    recap = None
    # the latest day whose games are over: the chosen day itself once its box scores are in
    for day in [d["date"] for d in service.days() if d["date"] <= chosen["date"]][:RECAP_LOOKBACK]:
        if games.empty:
            break
        found = today if day == chosen["date"] else perfect_props.find(_every_book(day), games, day)
        done = [p for p in perfect_props.grade(found, games, day) if p["hit"] is not None]
        if done:
            recap = {"date": day, "hit": sum(p["hit"] for p in done), "total": len(done), "props": done}
            break
    if recap and recap["date"] == chosen["date"]:
        today = []                    # the day is over: its list is the recap now

    def with_photo(props: list[dict]) -> list[dict]:
        return [{**p, "photo": nba_parlay.headshot_url(p["player_id"])} for p in props]
    if recap:
        recap = {**recap, "props": with_photo(recap["props"])}
    return {"date": chosen["date"], "book": chosen["book"], "props": with_photo(today), "recap": recap}
