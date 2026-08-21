import pytest

from edgefinder.betting import odds_math as om


def test_american_to_decimal_favorite():
    assert om.american_to_decimal(-150) == pytest.approx(1.6667, abs=1e-4)


def test_american_to_decimal_underdog():
    assert om.american_to_decimal(130) == pytest.approx(2.30)


def test_decimal_round_trips_american():
    for american in (-500, -150, -110, 100, 130, 500):
        decimal = om.american_to_decimal(american)
        assert om.decimal_to_american(decimal) == pytest.approx(american)


def test_implied_prob_of_even_money():
    assert om.implied_prob(100) == pytest.approx(0.5)


def test_implied_prob_of_standard_juice():
    assert om.implied_prob(-110) == pytest.approx(0.5238, abs=1e-4)


def test_devig_two_way_sums_to_one():
    fair_a, fair_b = om.devig_two_way(0.5238, 0.5238)
    assert fair_a + fair_b == pytest.approx(1.0)
    assert fair_a == pytest.approx(0.5)


def test_market_hold_standard_line():
    hold = om.market_hold(om.implied_prob(-110), om.implied_prob(-110))
    assert hold == pytest.approx(0.0476, abs=1e-4)


def test_prob_to_american_favorite():
    assert om.prob_to_american(0.60) == pytest.approx(-150)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        om.american_to_decimal(0)
    with pytest.raises(ValueError):
        om.prob_to_decimal(1.0)
    with pytest.raises(ValueError):
        om.devig_two_way(0.0, 0.0)
