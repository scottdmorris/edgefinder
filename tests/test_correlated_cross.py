"""Bets on different stats: measured values, and the same player's own stats."""

import math

import pytest

from edgefinder.betting import correlated
from edgefinder.betting.correlated import Leg


def leg(player, stat, team="AAA", over=True, prob=0.5, odds=100):
    return Leg(player=player, event_id="e1", team=team, is_over=over, prob=prob,
               american_odds=odds, stat=stat)


def coin_flips(rho):
    """P(both of two fair coin flips) at correlation rho."""
    return 0.25 + math.asin(rho) / (2 * math.pi)


def test_every_pair_of_stats_has_a_measured_value_in_range():
    stats = ["points", "rebounds", "assists", "threes"]
    pairs = {tuple(sorted((a, b))) for a in stats for b in stats if a < b}
    assert set(correlated.CROSS_CORRELATIONS) == pairs
    for same, mates, opps in correlated.CROSS_CORRELATIONS.values():
        assert 0.0 < same < 0.8 and abs(mates) < 0.1 and abs(opps) < 0.05


def test_one_players_points_and_threes_overs_are_far_likelier_together_than_apart():
    # same player, +0.719: P = 1/4 + asin(0.719) / (2 pi) = 0.3775, against 0.25 if independent
    joint = correlated.joint_probability([leg("A", "points"), leg("A", "threes")])
    assert joint == pytest.approx(coin_flips(0.719), abs=1e-5)
    assert joint == pytest.approx(0.3775, abs=1e-3)


def test_an_over_with_an_under_on_the_same_player_moves_the_other_way():
    joint = correlated.joint_probability([leg("A", "points"), leg("A", "threes", over=False)])
    assert joint == pytest.approx(0.5 - coin_flips(0.719), abs=1e-5)       # 0.1225


def test_two_players_stats_use_the_teammate_and_opponent_values_not_the_same_player_one():
    mates = correlated.joint_probability([leg("A", "points"), leg("B", "threes")])
    foes = correlated.joint_probability([leg("A", "points"), leg("B", "threes", team="BBB")])
    assert mates == pytest.approx(coin_flips(-0.021), abs=1e-5)
    assert foes == pytest.approx(coin_flips(0.008), abs=1e-5)


def test_three_stats_for_one_player_still_price_and_beat_independence():
    legs = [leg("A", "points"), leg("A", "rebounds"), leg("A", "threes")]
    joint = correlated.joint_probability(legs)
    assert 0.125 < joint < 0.5                       # above 1/8, below the weakest leg


def test_the_same_number_twice_is_still_refused():
    with pytest.raises(ValueError, match="once per stat"):
        correlated.joint_probability([leg("A", "points"), leg("A", "points", over=False)])


def test_an_override_still_applies_to_different_players_but_not_to_one_players_own_stats():
    legs = [leg("A", "points"), leg("B", "assists")]
    assert correlated.joint_probability(legs, teammate_rho=0.5) == pytest.approx(1 / 3, abs=1e-6)
    same = [leg("A", "points"), leg("A", "threes")]
    assert correlated.joint_probability(same, teammate_rho=0.5) == pytest.approx(
        coin_flips(0.719), abs=1e-5)


def test_the_slip_lets_one_player_back_two_stats_but_replaces_a_second_price_on_one_stat():
    from edgefinder.tracking import nba_parlay
    keys = ["1|points", "1|points", "1|threes", "2|points"]
    assert nba_parlay.toggle_leg([0], 1, keys) == [1]          # same player, same stat: replaced
    assert nba_parlay.toggle_leg([0], 2, keys) == [0, 2]       # same player, other stat: kept
    assert nba_parlay.toggle_leg([0, 2], 3, keys) == [0, 2, 3]
