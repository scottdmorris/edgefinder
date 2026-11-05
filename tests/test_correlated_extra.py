"""Hand-verified checks on the correlated parlay math.

For two standard-normal scores with correlation r, the chance both land at or
below their medians is 1/4 + arcsin(r) / (2 pi). Every 50% leg below sits on
the median, so that closed form gives exact expected values.
"""

import math
import random

import pytest

from edgefinder.betting import correlated
from edgefinder.betting.correlated import Leg


def leg(player, prob=0.5, over=True, team="BOS", event="e1", odds=100, stat="points"):
    return Leg(player=player, event_id=event, team=team, is_over=over, prob=prob,
               american_odds=odds, stat=stat)


def quarter_plus(r):
    return 0.25 + math.asin(r) / (2 * math.pi)


# ---- closed-form checks -------------------------------------------------------

def test_two_overs_with_rho_one_half_hit_together_a_third_of_the_time():
    # 1/4 + arcsin(0.5)/(2 pi) = 1/4 + (pi/6)/(2 pi) = 1/4 + 1/12
    legs = [leg("A"), leg("B")]
    assert correlated.joint_probability(legs, teammate_rho=0.5) == pytest.approx(1 / 3, abs=1e-6)


def test_an_over_and_an_under_on_positively_correlated_players_hit_together_a_sixth():
    # the under flips the sign: effective rho = -0.5 -> 1/4 - 1/12
    legs = [leg("A", over=True), leg("B", over=False)]
    assert correlated.joint_probability(legs, teammate_rho=0.5) == pytest.approx(1 / 6, abs=1e-6)


def test_two_unders_behave_like_two_overs():
    legs = [leg("A", over=False), leg("B", over=False)]
    assert correlated.joint_probability(legs, teammate_rho=0.5) == pytest.approx(1 / 3, abs=1e-6)


def test_opponents_use_the_opponent_correlation():
    legs = [leg("A", team="BOS"), leg("B", team="MIL")]
    assert correlated.joint_probability(legs, opponent_rho=0.5) == pytest.approx(1 / 3, abs=1e-6)
    # the teammate override must not touch an opposing pair
    assert correlated.joint_probability(legs, teammate_rho=0.9, opponent_rho=0.0) \
        == pytest.approx(0.25, abs=1e-6)


def test_zero_correlation_is_the_plain_product():
    legs = [leg("A", prob=0.62), leg("B", prob=0.37)]
    assert correlated.joint_probability(legs, teammate_rho=0.0) \
        == pytest.approx(0.62 * 0.37, abs=1e-6)


def test_measured_teammate_correlation_nudges_the_joint_down():
    # points teammates rho = -0.026: 0.25 + arcsin(-0.026)/(2 pi) = 0.25 - 0.004138
    legs = [leg("A"), leg("B")]
    assert correlated.joint_probability(legs) == pytest.approx(0.245862, abs=1e-5)


def test_measured_opponent_correlation_nudges_the_joint_up():
    # opponents rho = +0.023: 0.25 + 0.003661
    legs = [leg("A", team="BOS"), leg("B", team="MIL")]
    assert correlated.joint_probability(legs) == pytest.approx(0.253661, abs=1e-5)


def test_each_stat_uses_its_own_measured_correlation():
    # rebounds teammates rho = -0.005: 0.25 - arcsin(0.005)/(2 pi) = 0.25 - 0.000796
    legs = [leg("A", stat="rebounds"), leg("B", stat="rebounds")]
    assert correlated.joint_probability(legs) == pytest.approx(0.249204, abs=1e-5)


def test_an_unmeasured_stat_falls_back_to_the_points_correlation():
    legs = [leg("A", stat="blocks"), leg("B", stat="blocks")]
    assert correlated.joint_probability(legs) == pytest.approx(0.245862, abs=1e-5)


def test_bets_on_different_stats_are_independent_unless_overridden():
    legs = [leg("A", stat="points"), leg("B", stat="assists")]
    assert correlated.joint_probability(legs) == pytest.approx(0.25, abs=1e-9)
    # an explicit override applies to every pair regardless of stat
    assert correlated.joint_probability(legs, teammate_rho=0.5) == pytest.approx(1 / 3, abs=1e-6)


def test_legs_in_different_games_multiply_exactly():
    legs = [leg("A", prob=0.6, event="e1"), leg("B", prob=0.7, event="e2"),
            leg("C", prob=0.5, event="e3")]
    assert correlated.joint_probability(legs) == pytest.approx(0.6 * 0.7 * 0.5, abs=1e-12)


def test_games_are_priced_separately_and_multiplied():
    # game 1: two overs at rho 0.5 = 1/3 ; game 2: one lone 40% leg
    legs = [leg("A", event="e1"), leg("B", event="e1"), leg("C", prob=0.4, event="e2")]
    assert correlated.joint_probability(legs, teammate_rho=0.5) \
        == pytest.approx(1 / 3 * 0.4, abs=1e-6)


def test_leg_order_does_not_change_the_answer():
    legs = [leg("A", event="e2"), leg("B", event="e1"), leg("C", event="e2", prob=0.4)]
    forward = correlated.joint_probability(legs, teammate_rho=0.3)
    backward = correlated.joint_probability(list(reversed(legs)), teammate_rho=0.3)
    assert forward == pytest.approx(backward, abs=1e-9)


def test_a_single_leg_returns_its_own_probability():
    assert correlated.joint_probability([leg("A", prob=0.37)]) == 0.37


# ---- validation ----------------------------------------------------------------------

def test_an_empty_parlay_is_rejected():
    with pytest.raises(ValueError, match="at least one"):
        correlated.joint_probability([])


def test_the_same_player_twice_in_one_game_is_rejected():
    with pytest.raises(ValueError, match="only appear once"):
        correlated.joint_probability([leg("A"), leg("A", over=False)])


def test_the_same_player_in_two_different_games_is_allowed():
    legs = [leg("A", event="e1"), leg("A", event="e2")]
    assert correlated.joint_probability(legs) == pytest.approx(0.25)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.2, 1.3])
def test_probabilities_must_be_strictly_inside_zero_one(bad):
    with pytest.raises(ValueError, match="strictly between"):
        correlated.joint_probability([leg("A", prob=bad)])


def test_three_legs_that_cannot_all_be_correlated_that_way_are_rejected():
    # equicorrelated 3x3 matrix has eigenvalue 1 + 2r = -0.2 at r = -0.6: not a valid matrix
    legs = [leg("A"), leg("B"), leg("C")]
    with pytest.raises(ValueError, match="cannot all hold"):
        correlated.joint_probability(legs, teammate_rho=-0.6)


# ---- properties ---------------------------------------------------------------------------

def _random_slip(rng):
    legs = []
    for i in range(rng.randint(1, 5)):
        legs.append(leg(f"P{i}", prob=rng.uniform(0.05, 0.95), over=rng.random() < 0.5,
                        team=rng.choice(["BOS", "MIL"]), event=rng.choice(["e1", "e2"]),
                        odds=rng.choice([-250, -110, 120, 300])))
    return legs


def test_joint_probability_is_a_probability_and_never_beats_the_weakest_leg():
    rng = random.Random(2026)
    for _ in range(15):
        slip = _random_slip(rng)
        joint = correlated.joint_probability(slip)
        assert 0.0 <= joint <= 1.0
        assert joint <= min(leg_.prob for leg_ in slip) + 1e-6


def test_joint_probability_is_never_below_the_frechet_floor():
    # P(all) >= sum(p_i) - (n - 1)
    rng = random.Random(77)
    for _ in range(15):
        slip = _random_slip(rng)
        floor = max(0.0, sum(leg_.prob for leg_ in slip) - (len(slip) - 1))
        assert correlated.joint_probability(slip) >= floor - 1e-6


def test_stronger_positive_correlation_raises_the_chance_both_overs_hit():
    legs = [leg("A", prob=0.4), leg("B", prob=0.6)]
    chances = [correlated.joint_probability(legs, teammate_rho=r) for r in (-0.5, 0.0, 0.5, 0.9)]
    assert chances == sorted(chances)
    assert chances[0] < chances[1] < chances[2] < chances[3]
    assert chances[3] <= 0.4 + 1e-6


def test_independent_probability_is_the_product_and_decimal_odds_multiply():
    legs = [leg("A", prob=0.6, odds=100, event="e1"), leg("B", prob=0.5, odds=150, event="e2")]
    assert correlated.independent_probability(legs) == pytest.approx(0.3)
    assert correlated.decimal_odds(legs) == pytest.approx(5.0)   # 2.0 * 2.5


# ---- price helpers -----------------------------------------------------------------------------

@pytest.mark.parametrize("decimal, american", [
    (2.0, 100), (2.5, 150), (3.5, 250), (1.5, -200), (1.25, -400), (11.0, 1000)])
def test_decimal_to_american_hand_values(decimal, american):
    assert correlated.decimal_to_american(decimal) == american


@pytest.mark.parametrize("bad", [1.0, 0.5, -1.0])
def test_decimal_to_american_rejects_odds_that_pay_nothing(bad):
    with pytest.raises(ValueError):
        correlated.decimal_to_american(bad)


@pytest.mark.parametrize("prob, american", [
    (0.25, 300),      # 100 * 0.75 / 0.25
    (0.75, -300),     # -100 * 0.75 / 0.25
    (0.5, -100),
    (0.2, 400),
    (0.8, -400),
])
def test_fair_american_hand_values(prob, american):
    assert correlated.fair_american(prob) == american


def test_fair_american_clamps_certainties_instead_of_dividing_by_zero():
    assert correlated.fair_american(0.0) == 99900     # clamps to p = 0.001
    assert correlated.fair_american(1.0) == -99900    # clamps to p = 0.999
    assert correlated.fair_american(-5.0) == 99900
    assert correlated.fair_american(7.0) == -99900


def test_summarise_hand_worked_two_game_slip():
    # independent: 0.5 * 0.5 = 0.25 ; decimal 2.2 * 2.2 = 4.84 ; EV = 0.25*3.84 - 0.75 = 0.21
    legs = [leg("A", odds=120, event="e1"), leg("B", odds=120, event="e2")]
    summary = correlated.summarise(legs)
    assert summary["legs"] == 2
    assert summary["joint_probability"] == pytest.approx(0.25)
    assert summary["independent_probability"] == pytest.approx(0.25)
    assert summary["decimal_odds"] == pytest.approx(4.84)
    assert summary["payout_per_unit"] == pytest.approx(3.84)
    assert summary["fair_american"] == 300
    assert summary["ev_per_unit"] == pytest.approx(0.21)


def test_summarise_uses_the_correlated_joint_for_ev_not_the_product():
    legs = [leg("A", odds=100), leg("B", odds=100)]        # same game, teammates
    summary = correlated.summarise(legs, teammate_rho=0.5)
    # joint 1/3 vs independent 1/4 at decimal 4.0: EV = (1/3)*3 - 2/3 = 1/3
    assert summary["joint_probability"] == pytest.approx(1 / 3, abs=1e-6)
    assert summary["independent_probability"] == pytest.approx(0.25)
    assert summary["ev_per_unit"] == pytest.approx(1 / 3, abs=1e-5)
