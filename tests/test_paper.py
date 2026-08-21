import pytest

from edgefinder.tracking import paper


def _ml_row(side="home", odds=-120):
    return {"market": "ml", "side": side, "line": None, "american_odds": odds}


def _total_row(side="over", line=8.5, odds=-110):
    return {"market": "total", "side": side, "line": line, "american_odds": odds}


def test_ml_home_win():
    result, pnl = paper.grade_pick(_ml_row("home", -120), 5, 3)
    assert result == "win"
    assert pnl == pytest.approx(100 / 120)


def test_ml_away_loss():
    result, pnl = paper.grade_pick(_ml_row("away", 150), 5, 3)
    assert result == "loss"
    assert pnl == -1.0


def test_total_over_win():
    result, pnl = paper.grade_pick(_total_row("over", 8.5), 6, 3)
    assert result == "win"


def test_total_under_win():
    result, _ = paper.grade_pick(_total_row("under", 8.5), 4, 4)
    assert result == "win"


def test_total_push_on_integer_line():
    result, pnl = paper.grade_pick(_total_row("over", 9.0), 5, 4)
    assert result == "push"
    assert pnl == 0.0


def test_best_pick_takes_highest_ev():
    game = {
        "home": "H", "away": "A",
        "home_ml": -120, "away_ml": 100,
        "p_home_bet": 0.55, "p_away_bet": 0.45,
        "home_ml_ev": 0.031, "away_ml_ev": -0.02,
        "total_line": 8.5, "over_odds": -110, "under_odds": -110,
        "p_over_bet": 0.55, "p_under_bet": 0.45,
        "over_ev": 0.05, "under_ev": -0.06,
    }
    pick = paper._best_pick(game)
    assert pick["market"] == "total"
    assert pick["side"] == "over"


def test_best_pick_none_when_below_threshold():
    game = {"home_ml_ev": 0.01, "away_ml_ev": -0.03}
    assert paper._best_pick(game) is None
