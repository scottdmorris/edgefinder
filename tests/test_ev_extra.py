"""Hand-verified expected value and Kelly sizing."""

import math
import random

import pytest

from edgefinder.betting import ev
from edgefinder.betting.odds_math import american_to_decimal

def test_minus_110_pays_twenty_one_elevenths():
    # 1 + 100/110 = 210/110 = 21/11, the figure the cases below rely on
    assert american_to_decimal(-110) == pytest.approx(21 / 11)


# ---- expected value ---------------------------------------------------------

@pytest.mark.parametrize("prob, decimal, expected", [
    (0.5, 2.0, 0.0),          # 0.5 * 1 - 0.5
    (0.6, 2.0, 0.2),          # 0.6 * 1 - 0.4
    (0.4, 2.0, -0.2),
    (0.55, 21 / 11, 0.05),    # 0.55 * 10/11 = 0.5 ; 0.5 - 0.45
    (0.25, 4.0, 0.0),         # 0.25 * 3 - 0.75
    (0.0, 5.0, -1.0),         # certain loss costs the whole unit
    (1.0, 5.0, 4.0),          # certain win collects the profit
])
def test_ev_per_unit_hand_values(prob, decimal, expected):
    assert ev.ev_per_unit(prob, decimal) == pytest.approx(expected)


def test_ev_is_linear_in_probability():
    low, high = ev.ev_per_unit(0.3, 3.0), ev.ev_per_unit(0.7, 3.0)
    mid = ev.ev_per_unit(0.5, 3.0)
    assert mid == pytest.approx((low + high) / 2)


def test_ev_breaks_even_exactly_at_the_implied_probability():
    for decimal in (1.25, 1.5, 2.0, 3.7, 10.0):
        assert ev.ev_per_unit(1.0 / decimal, decimal) == pytest.approx(0.0, abs=1e-12)


# ---- Kelly ------------------------------------------------------------------

@pytest.mark.parametrize("prob, decimal, expected", [
    (0.6, 2.0, 0.2),            # b=1: (0.6 - 0.4) / 1
    (0.55, 21 / 11, 0.055),     # b=10/11: 0.05 / (10/11)
    (0.5, 3.0, 0.25),           # b=2: (1.0 - 0.5) / 2
    (0.4, 2.0, 0.0),            # -EV: never bet
    (0.5, 2.0, 0.0),            # exactly fair: no edge, no bet
])
def test_kelly_fraction_hand_values(prob, decimal, expected):
    assert ev.kelly_fraction(prob, decimal) == pytest.approx(expected)


@pytest.mark.parametrize("decimal", [1.0, 0.5, 0.0, -2.0])
def test_kelly_is_zero_when_the_bet_pays_nothing(decimal):
    assert ev.kelly_fraction(0.99, decimal) == 0.0


def test_kelly_is_never_negative_and_never_exceeds_the_win_probability():
    rng = random.Random(1)
    for _ in range(500):
        prob, decimal = rng.random(), rng.uniform(1.01, 30.0)
        fraction = ev.kelly_fraction(prob, decimal)
        assert 0.0 <= fraction <= prob + 1e-12   # f* = p - q/b <= p


def test_kelly_maximises_long_run_log_growth():
    prob, decimal = 0.55, 21 / 11
    b = decimal - 1.0

    def growth(f):
        return prob * math.log(1 + b * f) + (1 - prob) * math.log(1 - f)

    best = ev.kelly_fraction(prob, decimal)
    assert growth(best) > growth(best * 0.5)
    assert growth(best) > growth(best * 1.5)
    assert growth(best) > growth(0.0)


# ---- stake sizing -------------------------------------------------------------

def test_stake_is_quarter_kelly_of_the_bankroll():
    # kelly 0.055 * 0.25 = 0.01375 ; * 1000 = 13.75
    assert ev.recommended_stake(1000, 0.55, 21 / 11) == 13.75


def test_stake_is_capped_at_five_percent_of_bankroll():
    # kelly 0.4 * 0.25 = 0.10 > 0.05 cap -> 5% of 1000
    assert ev.recommended_stake(1000, 0.7, 2.0) == 50.0


def test_stake_rounds_to_cents():
    # 0.01375 * 333.33 = 4.5832875 -> 4.58
    assert ev.recommended_stake(333.33, 0.55, 21 / 11) == 4.58


def test_negative_edge_stakes_nothing():
    assert ev.recommended_stake(1000, 0.4, 2.0) == 0.0


@pytest.mark.parametrize("bankroll", [0, -50.0])
def test_empty_or_negative_bankroll_stakes_nothing(bankroll):
    assert ev.recommended_stake(bankroll, 0.9, 2.0) == 0.0


def test_custom_multiplier_and_cap():
    # full Kelly 0.2, multiplier 1.0 -> 0.2 but cap 0.10 -> 100 on 1000
    assert ev.recommended_stake(1000, 0.6, 2.0, kelly_multiplier=1.0, max_fraction=0.10) == 100.0
    # same bet, multiplier 0.5, cap loose -> 0.1 -> 100 as well; cap tighter -> 30
    assert ev.recommended_stake(1000, 0.6, 2.0, kelly_multiplier=0.5, max_fraction=0.03) == 30.0


def test_stake_stays_between_zero_and_the_cap_for_random_bets():
    rng = random.Random(9)
    for _ in range(500):
        bankroll = rng.uniform(1, 5000)
        stake = ev.recommended_stake(bankroll, rng.random(), rng.uniform(1.01, 20.0))
        assert 0.0 <= stake <= round(bankroll * ev.MAX_BANKROLL_FRACTION, 2) + 0.01


def test_a_stake_is_never_negative_even_with_a_bad_multiplier():
    assert ev.recommended_stake(1000, 0.6, 2.0, kelly_multiplier=-1) >= 0.0
