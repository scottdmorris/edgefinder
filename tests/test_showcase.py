"""The game simulation and Perfect Props."""

import numpy as np
import pandas as pd
import pytest

from edgefinder.tracking import game_sim, perfect_props


def _player(pid, team, points, lines=()):
    return game_sim.Player(pid, f"P{pid}", team, {"points": points, "rebounds": 5.0, "assists": 3.0,
                                                  "threes": 1.5}, {"points": list(lines)})


def _game(home_points=25.0, away_points=20.0, runs=4000, seed=1):
    players = [_player(i, "HOM", home_points, (24.5,)) for i in range(1, 6)] + \
              [_player(i, "AWY", away_points) for i in range(6, 11)]
    return game_sim.simulate(players, "AWY", "HOM", {"HOM": 0.0, "AWY": 0.0}, runs=runs, seed=seed)


def test_the_team_projected_to_score_more_wins_more_often_and_the_chances_add_up():
    result = _game()
    home, away = result["teams"]["HOM"], result["teams"]["AWY"]
    assert home["win_pct"] > 80 and home["win_pct"] + away["win_pct"] == pytest.approx(100)
    assert home["average"] == pytest.approx(125, abs=2) and away["average"] == pytest.approx(100, abs=2)


def test_scores_swing_like_real_games_not_like_ten_independent_players():
    margin = _game()["margin"]
    assert 18 <= margin["high"] - margin["low"] <= 45        # 10th to 90th percentile of the margin


def test_a_props_chance_is_the_models_own_spread_around_its_projection():
    stats = next(p for p in _game()["players"] if p["player_id"] == 1)["stats"]["points"]
    assert stats["average"] == pytest.approx(25, abs=0.6)
    over = stats["lines"][0]
    assert over["line"] == 24.5 and over["over_pct"] == pytest.approx(48, abs=3)


def test_the_same_seed_gives_the_same_game_and_the_margin_chart_covers_every_run():
    first, again = _game(seed=7), _game(seed=7)
    assert first["typical"] == again["typical"]
    assert sum(bar["pct"] for bar in first["margin_chart"]) == pytest.approx(100, abs=0.5)


def test_the_typical_games_box_score_adds_up_to_its_final_score():
    typical = _game()["typical"]
    for team in ("HOM", "AWY"):
        listed = sum(row["points"] for row in typical["box"] if row["team"] == team)
        assert listed + typical["rest"][team] == typical["score"][team]


# ---- perfect props ---------------------------------------------------------------------------

def _logs(points, rebounds=None, start="2026-11-01"):
    days = pd.date_range(start, periods=len(points))
    return pd.DataFrame({"player_id": 1, "game_date": days, "season": "2026-27", "pts": points,
                         "reb": rebounds or [5] * len(points), "ast": 3, "fg3m": 1})


def _table(*legs):
    rows = [{"Side": side, "line": line, "Odds": odds, "player_id": 1, "Player": "Jalen", "Game": "A @ B",
             "event_id": "e1", "stat_key": stat, "Leg": f"Jalen · {bet}"} for side, line, odds, stat, bet in legs]
    return pd.DataFrame(rows, index=range(100, 100 + len(rows)))


def test_the_hardest_line_cleared_in_every_game_is_kept_best_price_first():
    logs = _logs([12, 15, 18, 11, 20, 14, 13, 16])          # never under 11
    table = _table(("Over", 9.5, -900, "points", "Over 9.5 points"),
                   ("10+", 9.5, -1100, "points", "10+ points"),
                   ("Over", 12.5, -300, "points", "Over 12.5 points"),       # missed once (11)
                   ("15+", 14.5, 200, "points", "15+ points"))
    found = perfect_props.find(table, logs, "2026-11-20")
    assert [(p["bet"], p["odds"], p["games"]) for p in found] == [("Over 9.5 points", -900, 8)]


def test_too_few_games_or_a_rung_fanduel_does_not_offer_is_not_a_perfect_prop():
    assert perfect_props.find(_table(("Over", 5.5, -500, "points", "Over 5.5 points")),
                              _logs([10] * 5), "2026-11-20") == []
    assert perfect_props.find(_table(("7+", 6.5, -500, "points", "7+ points")),
                              _logs([10] * 9), "2026-11-20") == []


def test_grading_says_hit_or_miss_from_that_nights_box_score_and_none_without_one():
    logs = _logs([12] * 8 + [9])
    found = perfect_props.find(_table(("Over", 9.5, -900, "points", "Over 9.5 points")), logs, "2026-11-09")
    assert [p["hit"] for p in perfect_props.grade(found, logs, "2026-11-09")] == [False]
    assert [p["hit"] for p in perfect_props.grade(found, logs, "2026-11-10")] == [None]
    assert np.isnan(perfect_props.grade(found, logs.assign(pts=np.nan), "2026-11-09")[0]["actual"])
