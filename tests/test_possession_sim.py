"""The possession-by-possession game: its box scores add up, it is repeatable, and it is tuned to
the model's projected scores."""

import random

import numpy as np
import pandas as pd
import pytest

from edgefinder.tracking import possession_sim as ps


def _logs(pts=20, fga=16, fta=5, fg3m=2, reb=6, ast=4, tov=2, minutes=32, games=15):
    return pd.DataFrame({"game_date": pd.date_range("2026-10-20", periods=games), "minutes": minutes,
                         "fga": fga, "fta": fta, "fg3m": fg3m, "pts": pts, "reb": reb, "ast": ast,
                         "tov": tov, "stl": 1, "blk": 1})


def _roster(team, first_id, points=20):
    players = [ps.profile(f"{team} P{i}", first_id + i, team, _logs(pts=points), minutes=32) for i in range(5)]
    players += ps.bench(team, ps.TEAM_MINUTES - 160, 25.0, 2, first_id=-first_id)
    return ps.starters(players)


ROSTERS = {"AWY": _roster("AWY", 100), "HOM": _roster("HOM", 200)}


def test_a_profile_reads_a_players_rates_and_too_few_minutes_is_none():
    p = ps.profile("A", 1, "T", _logs())
    assert p.minutes == 32 and p.three_share == pytest.approx(2 / 0.36 / 16)
    assert 0 < p.tov_share < p.trip_share < 1
    assert ps.profile("A", 1, "T", _logs(minutes=1, games=5)) is None


def test_a_game_ends_with_a_winner_and_every_point_is_in_someones_box_score():
    game = ps.play_game(ROSTERS, "AWY", "HOM", 99.0, random.Random(3), record=True)
    assert game["score"]["AWY"] != game["score"]["HOM"]
    for team, roster in ROSTERS.items():
        assert sum(game["box"][p.player_id]["points"] for p in roster) == game["score"][team]
    events = game["events"]
    assert events[0]["kind"] == "start" and events[-1]["kind"] == "final"
    assert (events[-1]["away"], events[-1]["home"]) == (game["score"]["AWY"], game["score"]["HOM"])
    assert all(len(e["on"]["AWY"]) == 5 and len(e["on"]["HOM"]) == 5 for e in events)
    shots = [e for e in events if e["kind"] in ("make", "miss")]
    assert shots and all(0 <= e["x"] <= 100 and 0 <= e["y"] <= 100 for e in shots)


def test_shooting_is_tuned_so_each_teams_average_meets_its_target():
    targets = {"AWY": 100.0, "HOM": 118.0}
    result = ps.simulate(ROSTERS, "AWY", "HOM", 99.0, targets, runs=300, seed=5)
    assert result["scores"]["AWY"].mean() == pytest.approx(100, abs=4)
    assert result["scores"]["HOM"].mean() == pytest.approx(118, abs=4)
    assert (result["margin"] > 0).mean() > 0.75


def test_the_watched_game_is_the_typical_run_replayed_exactly():
    result = ps.simulate(ROSTERS, "AWY", "HOM", 99.0, {"AWY": 108.0, "HOM": 108.0}, runs=200, seed=9)
    watched = result["watched"]["score"]
    assert any(g["score"] == watched for g in result["games"])
    margin = watched["HOM"] - watched["AWY"]
    assert abs(margin - np.median(result["margin"])) <= result["margin"].std()


def test_win_chances_follow_the_score_and_settle_at_the_end():
    events = [{"t": 0, "away": 0, "home": 0}, {"t": 2400, "away": 90, "home": 100},
              {"t": 2880, "away": 100, "home": 101}]
    chances = [e["home_win"] for e in ps.win_chances(events, "A", "H", margin_mean=0.0, margin_sd=12.0)]
    assert chances[0] == pytest.approx(50, abs=0.1) and chances[1] > 90 and chances[2] == 100
