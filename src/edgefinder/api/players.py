"""The Players screen's data: anyone in the game logs, how they're playing, and their games, so
the page can show how often they've cleared any number without asking the server each time."""

import datetime as dt

import pandas as pd

from ..data import nba_live, nba_stats
from ..models import nba_stat_model
from ..tracking import nba_paper, nba_parlay, prop_history
from ..tracking import nba_player_lookup as lookup
from ..data import team_colors
from . import service

GAMES_SENT = 82              # a season's worth, newest first; enough for "this season" early on
RECENT_GAMES = 10            # the "last 10" average beside each line on the slate


def _history() -> pd.DataFrame:
    return service.load_games()


def line_history(player_id: int, date: dt.date, stat: str, line: float) -> dict:
    def build() -> dict:
        games = _history()
        if not games.empty:
            games = games[games["player_id"] == player_id]
        column = nba_stat_model.STATS[stat].column
        return prop_history.line_counts(prop_history.played_games(games, column), column,
                                        pd.Timestamp(date), line)

    return service.cached(("prop-history", player_id, date, stat, line), build)


def players() -> list[dict]:
    """Everyone who played this season (or in the logs at all, early on), for the search box."""
    history = _history()
    if history.empty:
        return []
    options = lookup.player_options(history, nba_stats.current_season(dt.date.today())) \
        or lookup.player_options(history)
    latest = history.sort_values("game_date").drop_duplicates("player_id", keep="last") \
        .set_index("player_id")
    return [{"id": int(pid), "name": latest.at[pid, "player_name"], "team": latest.at[pid, "team"],
             "plain": lookup.plain_letters(latest.at[pid, "player_name"])}
            for pid in options if pid in latest.index]


def _average(games: pd.DataFrame, column: str) -> float | None:
    return service._num(games[column].mean(), 1) if not games.empty else None


def _stat_line(rows: pd.DataFrame, stat: str, season: pd.DataFrame,
               recent: pd.DataFrame) -> dict:
    """One stat's FanDuel line beside the player's own averages and each model's projection."""
    first = rows.iloc[0]
    column = nba_stat_model.STATS[stat].column
    return {"stat": stat, "label": nba_stat_model.STATS[stat].label,
            "line": float(first["line"]), "over": int(first["over_odds"]),
            "under": int(first["under_odds"]),
            "season_avg": _average(season, column), "last10_avg": _average(recent, column),
            "projections": [{"model": service.model_short(r["model_version"]),
                             "mean": service._num(r["model_mean"], 1)}
                            for _, r in rows.drop_duplicates("model_version").iterrows()]}


def _tonight(player_id: int, season: pd.DataFrame, recent: pd.DataFrame) -> dict | None:
    """Every FanDuel line the player has on the latest slate, points first, each with his
    season and last-10 averages for that stat."""
    ledger = nba_paper.scope(service.load_ledger(), book=nba_paper.DEFAULT_BOOK)
    if ledger.empty:
        return None
    rows = ledger[(ledger["player_id"] == player_id)
                  & (ledger["game_date"] == ledger["game_date"].max())]
    if rows.empty:
        return None
    stats = rows["stat"].fillna(nba_paper.DEFAULT_STAT)
    first = rows.iloc[0]
    return {"date": first["game_date"], "game": f"{first['away']} @ {first['home']}",
            "lines": [_stat_line(rows[stats == stat], stat, season, recent)
                      for stat in nba_stat_model.STATS if (stats == stat).any()]}


def profile(player_id: int) -> dict:
    history = _history()
    games = lookup.player_games(history, player_id) if not history.empty else pd.DataFrame()
    if games.empty:
        raise service.NotFound(f"no games for player {player_id}")
    games = games.sort_values("game_date", ascending=False)
    latest = games.iloc[0]
    season = lookup.current_season_games(games)
    averages = lookup.season_averages(season)
    team = latest["team"]
    return {
        "id": int(player_id), "name": latest["player_name"], "team": team,
        "photo": nba_parlay.headshot_url(player_id), "logo": nba_live.logo_url(team),
        "color": team_colors.team_color(team), "season": averages.get("season", ""),
        "season_games": int(averages.get("games", len(season))),
        "averages": {k: service._num(averages.get(k), 1)
                     for k in ("pts", "reb", "ast", "fg3m", "minutes")},
        "tonight": _tonight(player_id, season, games.head(RECENT_GAMES)),
        "games": [{"date": pd.Timestamp(r["game_date"]).strftime("%Y-%m-%d"),
                   "opponent": r["opponent"], "home": bool(r["is_home"]), "result": r["wl"],
                   "season": r["season"], "minutes": round(float(r["minutes"])),
                   "pts": int(r["pts"]), "reb": int(r["reb"]), "ast": int(r["ast"]),
                   "fg3m": int(r["fg3m"])}
                  for r in games.head(GAMES_SENT).to_dict("records")],
    }
