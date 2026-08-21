import pytest

from edgefinder.betting import ev


def test_fair_coin_at_even_money_is_zero_ev():
    assert ev.ev_per_unit(0.5, 2.0) == pytest.approx(0.0)


def test_positive_edge_gives_positive_ev():
    # 55% true prob at even money: EV = 0.55 - 0.45 = +0.10
    assert ev.ev_per_unit(0.55, 2.0) == pytest.approx(0.10)


def test_negative_edge_gives_negative_ev():
    assert ev.ev_per_unit(0.45, 2.0) == pytest.approx(-0.10)


def test_kelly_fraction_known_value():
    # p=0.55 at even money: kelly = (0.55*1 - 0.45)/1 = 0.10
    assert ev.kelly_fraction(0.55, 2.0) == pytest.approx(0.10)


def test_kelly_fraction_never_negative():
    assert ev.kelly_fraction(0.40, 2.0) == 0.0


def test_recommended_stake_quarter_kelly():
    # full kelly 10% -> quarter kelly 2.5% of 1000 = 25
    stake = ev.recommended_stake(1000.0, 0.55, 2.0)
    assert stake == pytest.approx(25.0)


def test_recommended_stake_respects_cap():
    # huge edge would exceed the 5% cap
    stake = ev.recommended_stake(1000.0, 0.90, 3.0, kelly_multiplier=1.0)
    assert stake == pytest.approx(50.0)


def test_recommended_stake_zero_for_negative_ev():
    assert ev.recommended_stake(1000.0, 0.40, 2.0) == 0.0
