"""Hand-verified checks on odds conversion and vig removal."""

import math
import random

import pytest

from edgefinder.betting import odds_math as om

QUOTED = [-1000, -250, -200, -150, -110, 100, 105, 120, 150, 450, 2000]


# ---- american <-> decimal -------------------------------------------------

@pytest.mark.parametrize("american, decimal", [
    (150, 2.5),            # risk 100 to win 150: pays 2.5 per 1
    (100, 2.0),            # even money
    (-200, 1.5),           # risk 200 to win 100: 1 + 100/200
    (-100, 2.0),           # -100 is the same bet as +100
    (-110, 1 + 100 / 110),  # 1.90909...
    (-1000, 1.1),
    (2000, 21.0),
])
def test_american_to_decimal_hand_values(american, decimal):
    assert om.american_to_decimal(american) == pytest.approx(decimal)


def test_american_zero_is_rejected():
    with pytest.raises(ValueError):
        om.american_to_decimal(0)


@pytest.mark.parametrize("decimal, american", [
    (2.5, 150.0),          # (2.5 - 1) * 100
    (2.0, 100.0),          # boundary: even money is +100, not -100
    (1.5, -200.0),         # -100 / 0.5
    (1.25, -400.0),        # -100 / 0.25
    (11.0, 1000.0),
])
def test_decimal_to_american_hand_values(decimal, american):
    assert om.decimal_to_american(decimal) == pytest.approx(american)


@pytest.mark.parametrize("bad", [1.0, 0.99, 0.0, -2.0])
def test_decimal_at_or_below_one_is_rejected(bad):
    with pytest.raises(ValueError):
        om.decimal_to_american(bad)


@pytest.mark.parametrize("american", QUOTED)
def test_odds_round_trip_between_american_and_decimal(american):
    assert om.decimal_to_american(om.american_to_decimal(american)) == pytest.approx(american)


def test_minus_100_round_trips_to_plus_100_which_is_the_same_bet():
    back = om.decimal_to_american(om.american_to_decimal(-100))
    assert back == pytest.approx(100.0)


def test_decimal_round_trip_for_random_decimals():
    rng = random.Random(11)
    for _ in range(200):
        decimal = rng.uniform(1.01, 40.0)
        back = om.american_to_decimal(om.decimal_to_american(decimal))
        assert back == pytest.approx(decimal, rel=1e-9)


def test_longer_odds_always_pay_more():
    decimals = [om.american_to_decimal(a) for a in sorted(QUOTED)]
    assert decimals == sorted(decimals)


# ---- implied / fair probability -------------------------------------------

@pytest.mark.parametrize("american, prob", [
    (100, 0.5),
    (-110, 110 / 210),     # risk 110 to win 100: 110 / (110 + 100)
    (-200, 2 / 3),
    (200, 1 / 3),
    (300, 0.25),
])
def test_implied_prob_hand_values(american, prob):
    assert om.implied_prob(american) == pytest.approx(prob)


@pytest.mark.parametrize("american", QUOTED)
def test_implied_probability_is_strictly_inside_zero_one(american):
    assert 0.0 < om.implied_prob(american) < 1.0


@pytest.mark.parametrize("prob, decimal", [(0.25, 4.0), (0.5, 2.0), (0.8, 1.25)])
def test_prob_to_decimal_hand_values(prob, decimal):
    assert om.prob_to_decimal(prob) == pytest.approx(decimal)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.5])
def test_prob_to_decimal_rejects_certainties_and_nonsense(bad):
    with pytest.raises(ValueError):
        om.prob_to_decimal(bad)


@pytest.mark.parametrize("prob, american", [
    (0.25, 300.0),     # decimal 4 -> +300
    (0.75, -300.0),    # decimal 4/3 -> -100 / (1/3)
    (0.5, 100.0),
])
def test_fair_american_hand_values(prob, american):
    assert om.prob_to_american(prob) == pytest.approx(american)


def test_prob_to_american_and_implied_prob_are_inverses():
    for prob in (0.05, 0.2, 0.37, 0.5, 0.63, 0.9, 0.97):
        assert om.implied_prob(om.prob_to_american(prob)) == pytest.approx(prob)


# ---- vig removal ------------------------------------------------------------

def test_even_two_way_market_devigs_to_fifty_fifty():
    a, b = om.devig_two_way(om.implied_prob(-110), om.implied_prob(-110))
    assert a == pytest.approx(0.5) and b == pytest.approx(0.5)


def test_two_way_devig_hand_worked_example():
    # -130 -> 130/230 = 0.565217 ; -102 -> 102/202 = 0.504950 ; total 1.070168
    # fair over = 0.565217 / 1.070168 = 0.52816
    over, under = om.devig_two_way(om.implied_prob(-130), om.implied_prob(-102))
    assert over == pytest.approx(0.52816, abs=1e-5)
    assert under == pytest.approx(0.47184, abs=1e-5)


def test_two_way_devig_preserves_the_ratio_between_sides():
    over, under = om.devig_two_way(0.6, 0.45)
    assert over / under == pytest.approx(0.6 / 0.45)


def test_two_way_devig_rejects_an_empty_market():
    with pytest.raises(ValueError):
        om.devig_two_way(0.0, 0.0)


def test_devigged_probabilities_sum_to_one_and_stay_in_range():
    rng = random.Random(3)
    for _ in range(300):
        a, b = om.implied_prob(rng.choice(QUOTED)), om.implied_prob(rng.choice(QUOTED))
        fa, fb = om.devig_two_way(a, b)
        assert math.isclose(fa + fb, 1.0, abs_tol=1e-12)
        assert 0.0 < fa < 1.0 and 0.0 < fb < 1.0


def test_multiway_devig_hand_values():
    # total 1.2 -> 0.5/1.2, 0.3/1.2, 0.4/1.2
    fair = om.devig_multiway([0.5, 0.3, 0.4])
    assert fair == pytest.approx([5 / 12, 0.25, 1 / 3])


def test_multiway_devig_sums_to_one_for_random_markets():
    rng = random.Random(5)
    for _ in range(200):
        n = rng.randint(2, 6)
        fair = om.devig_multiway([rng.uniform(0.05, 0.9) for _ in range(n)])
        assert math.isclose(sum(fair), 1.0, abs_tol=1e-12)
        assert all(0.0 < p < 1.0 for p in fair)


@pytest.mark.parametrize("bad", [[0.5, 0.0, 0.5], [0.5, -0.1, 0.9], [0.0, 0.0], []])
def test_multiway_devig_rejects_non_positive_inputs(bad):
    with pytest.raises(ValueError):
        om.devig_multiway(bad)


def test_market_hold_hand_value():
    # two -110 sides: 2 * 110/210 - 1 = 10/210 = 1/21
    hold = om.market_hold(om.implied_prob(-110), om.implied_prob(-110))
    assert hold == pytest.approx(1 / 21)


def test_a_fair_market_has_no_hold():
    assert om.market_hold(0.6, 0.4) == pytest.approx(0.0)


def test_two_way_devig_refuses_a_negative_input_rather_than_return_a_chance_outside_zero_one():
    with pytest.raises(ValueError):
        om.devig_two_way(-0.2, 0.9)
