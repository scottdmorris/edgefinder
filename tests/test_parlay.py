import pytest

from edgefinder.betting.parlay import (
    ParlayLeg,
    leg_marginal_ev,
    parlay_decimal_odds,
    parlay_ev,
    parlay_true_prob,
)


def _leg(prob=0.5, odds=100, desc="leg"):
    return ParlayLeg(description=desc, model_prob=prob, american_odds=odds)


def test_true_prob_multiplies():
    legs = [_leg(0.6), _leg(0.5)]
    assert parlay_true_prob(legs) == pytest.approx(0.30)


def test_decimal_odds_multiply():
    legs = [_leg(odds=100), _leg(odds=100)]  # 2.0 * 2.0
    assert parlay_decimal_odds(legs) == pytest.approx(4.0)


def test_fair_legs_make_zero_ev_parlay():
    legs = [_leg(0.5, 100), _leg(0.5, 100)]
    assert parlay_ev(legs) == pytest.approx(0.0)


def test_vig_compounds_across_legs():
    # each leg -110 with 50% true prob is -EV; two legs are worse
    one = parlay_ev([_leg(0.5, -110)])
    two = parlay_ev([_leg(0.5, -110), _leg(0.5, -110)])
    assert one < 0
    assert two < one


def test_quoted_decimal_overrides_product():
    legs = [_leg(0.5, 100), _leg(0.5, 100)]
    # book quotes 3.6 instead of fair 4.0 -> negative EV
    assert parlay_ev(legs, quoted_decimal=3.6) == pytest.approx(0.25 * 2.6 - 0.75)


def test_marginal_ev_of_bad_leg_is_negative():
    good = _leg(0.60, 100)          # +EV leg
    bad = _leg(0.40, -120)          # clearly -EV leg
    assert leg_marginal_ev([good, bad], 1) < 0


def test_empty_parlay_is_zero():
    assert parlay_ev([]) == 0.0


def test_marginal_ev_index_validation():
    with pytest.raises(IndexError):
        leg_marginal_ev([_leg()], 3)
