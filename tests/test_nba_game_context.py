import pandas as pd
import pytest

from edgefinder.models import nba_game_context as gc


def side(game_id, date, team, opponent, pts, home, season="2025-26"):
    """One team's side of a game as two players who split the scoring."""
    return [{"player_id": hash((team, n)) % 10_000, "team": team, "opponent": opponent,
             "game_id": game_id, "game_date": pd.Timestamp(date), "season": season,
             "minutes": 30.0, "pts": pts / 2, "fga": 40, "fta": 10, "tov": 6, "is_home": home}
            for n in (1, 2)]


def game(game_id, date, home, away, home_pts, away_pts):
    return side(game_id, date, home, away, home_pts, True) + \
        side(game_id, date, away, home, away_pts, False)


def series(scores, home="AAA", away="BBB"):
    """AAA hosts BBB once a day; `scores` is a list of (AAA points, BBB points)."""
    rows = []
    for n, (home_pts, away_pts) in enumerate(scores, start=1):
        rows += game(f"g{n}", f"2025-11-{n:02d}", home, away, home_pts, away_pts)
    return pd.DataFrame(rows)


def row(table, team, game_id):
    return table[(table["team"] == team) & (table["game_id"] == game_id)].iloc[0]


STEADY = [(110, 100)] * 4     # AAA wins every game 110-100


def test_a_game_without_enough_history_has_no_numbers_rather_than_a_guess():
    first = row(gc.game_table(series(STEADY)), "AAA", "g1")
    assert pd.isna(first["exp_margin"]) and pd.isna(first["exp_total"])


def test_expected_points_come_from_own_scoring_and_the_opponents_defense():
    table = gc.game_table(series(STEADY))
    # before g4: AAA scores 110, BBB allows 110, the league averages 105 -> 115, plus
    # half the home edge; BBB scores 100, AAA allows 100 -> 95, minus half of it
    assert row(table, "AAA", "g4")["exp_team_pts"] == pytest.approx(115 + gc.HOME_EDGE / 2)
    assert row(table, "BBB", "g4")["exp_team_pts"] == pytest.approx(95 - gc.HOME_EDGE / 2)


def test_margin_and_total_are_the_difference_and_sum_of_the_two_sides():
    table = gc.game_table(series(STEADY))
    home, away = row(table, "AAA", "g4"), row(table, "BBB", "g4")
    assert home["exp_margin"] == pytest.approx(20 + gc.HOME_EDGE)
    assert home["exp_total"] == pytest.approx(210)
    assert away["exp_margin"] == pytest.approx(-home["exp_margin"])
    assert away["exp_total"] == pytest.approx(home["exp_total"])


def test_two_even_teams_differ_only_by_the_home_edge():
    table = gc.game_table(series([(100, 100)] * 4))
    assert row(table, "AAA", "g4")["exp_margin"] == pytest.approx(gc.HOME_EDGE)
    assert row(table, "BBB", "g4")["exp_margin"] == pytest.approx(-gc.HOME_EDGE)


def test_a_games_numbers_never_use_that_games_own_score():
    base = series(STEADY)
    changed = base.copy()
    changed.loc[(changed["game_id"] == "g4") & (changed["team"] == "AAA"), "pts"] = 90.0
    before, after = (row(gc.game_table(g), "AAA", "g4") for g in (base, changed))
    assert before["exp_margin"] == after["exp_margin"]
    assert before["exp_total"] == after["exp_total"]


def test_the_window_limits_how_far_back_the_form_looks():
    # an old blowout, then three even games: a window of 3 no longer sees the blowout
    games = series([(140, 80), (100, 100), (100, 100), (100, 100), (100, 100)])
    short = row(gc.game_table(games, window=3), "AAA", "g5")
    long = row(gc.game_table(games, window=10), "AAA", "g5")
    assert short["exp_margin"] == pytest.approx(gc.HOME_EDGE)
    assert long["exp_margin"] > short["exp_margin"]


def test_adding_game_context_keeps_every_row_and_its_order():
    games = series(STEADY)
    out = gc.add_game_context(games, games)
    assert list(out["game_id"]) == list(games["game_id"])
    assert list(out["player_id"]) == list(games["player_id"])
    assert set(gc.GAME_COLUMNS) <= set(out.columns)


def test_every_player_on_a_team_gets_his_teams_numbers():
    games = series(STEADY)
    out = gc.add_game_context(games, games)
    mine = out[(out["team"] == "BBB") & (out["game_id"] == "g4")]
    assert len(mine) == 2
    assert list(mine["exp_margin"]) == pytest.approx([-(20 + gc.HOME_EDGE)] * 2)

