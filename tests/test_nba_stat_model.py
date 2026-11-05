import pandas as pd
import pytest

from edgefinder.models import nba_stat_model


def test_every_stat_names_its_log_column_market_and_live_field():
    assert set(nba_stat_model.STATS) == {"points", "rebounds", "assists", "threes"}
    columns = {s.column for s in nba_stat_model.STATS.values()}
    assert columns == {"pts", "reb", "ast", "fg3m"}
    assert len({s.market for s in nba_stat_model.STATS.values()}) == 4
    assert all(s.dispersion > 0 for s in nba_stat_model.STATS.values())


def test_a_market_name_finds_its_stat():
    assert nba_stat_model.by_market("player_rebounds").key == "rebounds"
    with pytest.raises(StopIteration):
        nba_stat_model.by_market("player_unknown")


def games_for(team_abbr, column, values):
    rows = []
    for day, value in enumerate(values):
        rows.append({"player_id": 1, "player_name": "Jaylen Brown", "team": team_abbr,
                     "game_date": pd.Timestamp("2026-10-20") + pd.Timedelta(days=2 * day),
                     "season": "2026-27", "minutes": 34.0, "pts": 20.0, "reb": 5.0,
                     "ast": 3.0, "fg3m": 2.0, column: float(value)})
    return pd.DataFrame(rows)


EVENT = {"event_id": "e1", "home": "Boston Celtics", "away": "Milwaukee Bucks"}


@pytest.mark.parametrize("key,column,values", [
    ("points", "pts", [20, 30, 25, 25]),
    ("rebounds", "reb", [4, 8, 6, 6]),
    ("assists", "ast", [2, 6, 4, 4]),
    ("threes", "fg3m", [1, 3, 2, 2]),
])
def test_each_stat_projects_from_its_own_column(key, column, values):
    games = games_for("BOS", column, values)
    projection = nba_stat_model.project_event(
        nba_stat_model.STATS[key], EVENT, ["Jaylen Brown"], games, "2026-27", "2026-11-04")
    mean = projection["Jaylen Brown"]["mean"]
    assert min(values) <= mean <= max(values)


def test_the_stats_project_different_numbers_for_the_same_player():
    games = games_for("BOS", "pts", [20, 30, 25, 25])
    points = nba_stat_model.project_event(
        nba_stat_model.STATS["points"], EVENT, ["Jaylen Brown"], games, "2026-27", "2026-11-04")
    rebounds = nba_stat_model.project_event(
        nba_stat_model.STATS["rebounds"], EVENT, ["Jaylen Brown"], games, "2026-27", "2026-11-04")
    assert points["Jaylen Brown"]["mean"] > rebounds["Jaylen Brown"]["mean"]


def test_a_player_not_on_either_team_gets_no_projection():
    games = games_for("LAL", "pts", [20, 30, 25, 25])
    projection = nba_stat_model.project_event(
        nba_stat_model.STATS["points"], EVENT, ["Jaylen Brown"], games, "2026-27", "2026-11-04")
    assert projection == {}
