import pytest

from edgefinder.betting.suggest import (
    CandidateLeg,
    board_candidate_legs,
    suggest_parlays,
)


def _leg(game, prob, odds=None, ev=None, desc=None):
    return CandidateLeg(game, desc or f"{game}-{prob}", prob, odds, ev)


# ---------- odds mode ----------

def _pos_ev_legs():
    return [
        _leg("g1", 0.60, 100, 0.20),
        _leg("g2", 0.58, 105, 0.19),
        _leg("g3", 0.55, 110, 0.155),
        _leg("g4", 0.45, -110, -0.14),   # -EV, must be excluded
    ]


def test_odds_mode_excludes_negative_ev_legs():
    suggestions = suggest_parlays(_pos_ev_legs(), num_legs=2)
    used = {leg.game_key for s in suggestions for leg in s.legs}
    assert "g4" not in used


def test_odds_mode_ranks_by_parlay_ev():
    suggestions = suggest_parlays(_pos_ev_legs(), num_legs=2)
    evs = [s.ev for s in suggestions]
    assert evs == sorted(evs, reverse=True)
    assert all(ev > 0 for ev in evs)


def test_no_positive_ev_legs_means_no_suggestions():
    legs = [
        _leg("g1", 0.50, -110, -0.045),
        _leg("g2", 0.50, -110, -0.045),
        _leg("g3", 0.50, -110, -0.045),
    ]
    assert suggest_parlays(legs, num_legs=2) == []


def test_never_two_legs_from_same_game():
    legs = [
        _leg("g1", 0.60, 100, 0.20, desc="g1 home"),
        _leg("g1", 0.55, 120, 0.21, desc="g1 over"),
        _leg("g2", 0.58, 105, 0.19),
    ]
    for suggestion in suggest_parlays(legs, num_legs=2):
        keys = [leg.game_key for leg in suggestion.legs]
        assert len(keys) == len(set(keys))


def test_parlay_ev_math():
    legs = [_leg("g1", 0.60, 100, 0.20), _leg("g2", 0.60, 100, 0.20)]
    [suggestion] = suggest_parlays(legs, num_legs=2, top_n=1)
    assert suggestion.true_prob == pytest.approx(0.36)
    assert suggestion.decimal_odds == pytest.approx(4.0)
    assert suggestion.ev == pytest.approx(0.36 * 4.0 - 1.0)


# ---------- confidence mode (no odds) ----------

def test_confidence_mode_ranks_by_probability():
    legs = [
        _leg("g1", 0.62), _leg("g2", 0.60), _leg("g3", 0.58), _leg("g4", 0.56),
    ]
    suggestions = suggest_parlays(legs, num_legs=2)
    assert suggestions[0].true_prob == pytest.approx(0.62 * 0.60)
    assert suggestions[0].ev is None
    assert suggestions[0].decimal_odds is None


def test_confidence_mode_filters_weak_legs():
    legs = [_leg("g1", 0.70), _leg("g2", 0.65), _leg("g3", 0.51)]
    suggestions = suggest_parlays(legs, num_legs=2)
    used = {leg.game_key for s in suggestions for leg in s.legs}
    assert "g3" not in used


def test_requires_at_least_two_legs():
    with pytest.raises(ValueError):
        suggest_parlays([_leg("g1", 0.6)], num_legs=1)


# ---------- board extraction ----------

def test_board_candidate_legs_without_odds():
    board = [{
        "home": "H", "away": "A", "p_home": 0.55, "p_away": 0.45,
        "model_total": 8.6,
    }]
    legs = board_candidate_legs(board)
    assert len(legs) == 2  # no totals legs without a market line
    assert legs[0].american_odds is None


def test_board_candidate_legs_with_odds():
    board = [{
        "home": "H", "away": "A", "p_home": 0.55, "p_away": 0.45,
        "model_total": 10.0, "home_ml": -120, "away_ml": 102,
        "home_ml_ev": 0.02, "away_ml_ev": -0.06,
        "total_line": 8.5, "over_odds": -110, "under_odds": -110,
        "over_ev": 0.01, "under_ev": -0.05,
    }]
    legs = board_candidate_legs(board)
    assert len(legs) == 4
    over = next(l for l in legs if l.description.startswith("Over"))
    assert over.model_prob > 0.5  # model total 10.0 well above line 8.5
