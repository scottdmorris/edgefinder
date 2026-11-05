import pytest

from edgefinder.betting import correlated
from edgefinder.betting.correlated import Leg


def leg(player, event="e1", team="AAA", over=True, prob=0.5, odds=100):
    return Leg(player=player, event_id=event, team=team, is_over=over, prob=prob,
               american_odds=odds)


def test_legs_from_different_games_simply_multiply():
    legs = [leg("a", "e1", prob=0.6), leg("b", "e2", prob=0.5), leg("c", "e3", prob=0.4)]
    assert correlated.joint_probability(legs) == pytest.approx(0.6 * 0.5 * 0.4)


def test_a_single_leg_is_its_own_probability():
    assert correlated.joint_probability([leg("a", prob=0.37)]) == pytest.approx(0.37)


def test_with_no_correlation_same_game_legs_also_multiply():
    legs = [leg("a", prob=0.6), leg("b", team="BBB", prob=0.5)]
    assert correlated.joint_probability(legs, 0.0, 0.0) == pytest.approx(0.30, abs=1e-6)


def test_two_overs_for_opponents_are_likelier_together_when_opponents_correlate_up():
    legs = [leg("a", prob=0.5), leg("b", team="BBB", prob=0.5)]
    assert correlated.joint_probability(legs, 0.0, 0.5) > 0.25


def test_two_coin_flip_legs_match_the_known_bivariate_formula():
    # for two coin-flip legs with correlation r, P(both) = 1/4 + asin(r) / (2 pi)
    import math
    legs = [leg("a", prob=0.5), leg("b", team="BBB", prob=0.5)]
    r = 0.4
    assert correlated.joint_probability(legs, 0.0, r) == pytest.approx(
        0.25 + math.asin(r) / (2 * math.pi), abs=1e-5)


def test_an_over_and_an_under_move_against_each_other_when_players_correlate_up():
    over_under = [leg("a", prob=0.5), leg("b", team="BBB", over=False, prob=0.5)]
    both_over = [leg("a", prob=0.5), leg("b", team="BBB", prob=0.5)]
    assert correlated.joint_probability(over_under, 0.0, 0.4) < 0.25 \
        < correlated.joint_probability(both_over, 0.0, 0.4)


def test_the_measured_correlations_barely_move_a_same_game_pair():
    legs = [leg("a", prob=0.55), leg("b", prob=0.55), leg("c", team="BBB", prob=0.55)]
    assert correlated.joint_probability(legs) == pytest.approx(
        correlated.independent_probability(legs), abs=0.01)


def test_a_player_cannot_appear_twice():
    with pytest.raises(ValueError, match="only appear once"):
        correlated.joint_probability([leg("a", prob=0.5), leg("a", prob=0.4)])


def test_the_same_name_in_different_games_is_fine():
    assert correlated.joint_probability([leg("a", "e1"), leg("a", "e2")]) == pytest.approx(0.25)


def test_an_empty_slip_and_impossible_probabilities_are_rejected():
    with pytest.raises(ValueError):
        correlated.joint_probability([])
    with pytest.raises(ValueError, match="strictly between"):
        correlated.joint_probability([leg("a", prob=1.0)])


def test_correlations_that_cannot_hold_together_are_rejected():
    legs = [leg("a", team="AAA"), leg("b", team="AAA"), leg("c", team="AAA")]
    with pytest.raises(ValueError, match="cannot all hold"):
        correlated.joint_probability(legs, teammate_rho=-0.9, opponent_rho=0.0)


def test_payout_is_the_product_of_decimal_odds():
    legs = [leg("a", "e1", odds=100), leg("b", "e2", odds=-200)]
    assert correlated.decimal_odds(legs) == pytest.approx(2.0 * 1.5)


def stat_leg(player, stat, team="AAA", prob=0.5):
    return Leg(player=player, event_id="e1", team=team, is_over=True, prob=prob,
               american_odds=100, stat=stat)


def test_bets_on_different_stats_in_one_game_are_treated_as_independent():
    legs = [stat_leg("a", "points"), stat_leg("b", "rebounds", team="BBB")]
    assert correlated.joint_probability(legs) == pytest.approx(0.25, abs=1e-6)


def test_each_stat_uses_its_own_measured_correlation():
    import math
    # for two coin-flip legs with correlation r, P(both) = 1/4 + asin(r) / (2 pi)
    for stat, (_, opponents) in correlated.CORRELATIONS.items():
        legs = [stat_leg("a", stat), stat_leg("b", stat, team="BBB")]
        assert correlated.joint_probability(legs) == pytest.approx(
            0.25 + math.asin(opponents) / (2 * math.pi), abs=1e-4), stat


def test_every_stat_has_a_measured_correlation_pair_that_is_small():
    from edgefinder.models import nba_stat_model
    assert set(correlated.CORRELATIONS) == set(nba_stat_model.STATS)
    for teammates, opponents in correlated.CORRELATIONS.values():
        assert abs(teammates) < 0.1 and abs(opponents) < 0.1


def test_an_explicit_correlation_overrides_the_measured_one_for_every_stat():
    legs = [stat_leg("a", "points"), stat_leg("b", "rebounds", team="BBB")]
    assert correlated.joint_probability(legs, 0.0, 0.5) > 0.25


def test_decimal_odds_convert_to_american_both_ways():
    assert correlated.decimal_to_american(3.5) == 250
    assert correlated.decimal_to_american(2.0) == 100
    assert correlated.decimal_to_american(1.5) == -200
    with pytest.raises(ValueError):
        correlated.decimal_to_american(1.0)


def test_fair_odds_are_the_break_even_price_and_stay_finite():
    assert correlated.fair_american(0.5) == -100
    assert correlated.fair_american(0.25) == 300
    assert correlated.fair_american(0.0) > 0


def test_the_summary_reports_ev_against_the_payout():
    legs = [leg("a", "e1", prob=0.6, odds=100), leg("b", "e2", prob=0.6, odds=100)]
    summary = correlated.summarise(legs)
    assert summary["joint_probability"] == pytest.approx(0.36)
    assert summary["decimal_odds"] == pytest.approx(4.0)
    assert summary["ev_per_unit"] == pytest.approx(0.36 * 4.0 - 1.0)
    assert summary["fair_american"] == 178
