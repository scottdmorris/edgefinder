"""Hand-verified checks on the Poisson helpers and the board parlay suggester."""

import math

import pytest

from edgefinder.betting import poisson, suggest
from edgefinder.betting.suggest import CandidateLeg

E2 = math.exp(-2.0)


# ---- poisson -----------------------------------------------------------------------

def test_pmf_hand_values_at_lambda_two():
    assert poisson.pmf(0, 2.0) == pytest.approx(E2)          # e^-2
    assert poisson.pmf(1, 2.0) == pytest.approx(2 * E2)
    assert poisson.pmf(2, 2.0) == pytest.approx(2 * E2)      # 2^2 / 2!
    assert poisson.pmf(3, 2.0) == pytest.approx(4 / 3 * E2)  # 2^3 / 3!


def test_negative_counts_have_no_probability():
    assert poisson.pmf(-1, 2.0) == 0.0
    assert poisson.cdf(-1, 2.0) == 0.0


def test_cdf_adds_up_the_pmf():
    assert poisson.cdf(2, 2.0) == pytest.approx(5 * E2)      # 1 + 2 + 2


def test_half_point_line_cannot_push():
    probs = poisson.over_under_probs(2.5, 2.0)
    assert probs["push"] == 0.0
    assert probs["under"] == pytest.approx(5 * E2)            # P(X <= 2)
    assert probs["over"] == pytest.approx(1 - 5 * E2)


def test_whole_number_line_splits_over_under_push():
    probs = poisson.over_under_probs(2.0, 2.0)
    assert probs["push"] == pytest.approx(2 * E2)             # P(X = 2)
    assert probs["under"] == pytest.approx(3 * E2)            # P(X <= 1)
    assert probs["over"] == pytest.approx(1 - 5 * E2)         # P(X >= 3)
    assert probs["over"] + probs["under"] + probs["push"] == pytest.approx(1.0)


@pytest.mark.parametrize("lam", [0.0, -1.0])
def test_non_positive_lambda_is_rejected(lam):
    with pytest.raises(ValueError):
        poisson.over_under_probs(2.5, lam)


def test_no_push_probabilities_renormalise_to_one():
    # whole line 2, lambda 2: over 1-5e^-2, under 3e^-2, live mass 1 - 2e^-2
    probs = poisson.no_push_probs(2.0, 2.0)
    assert probs["over"] == pytest.approx((1 - 5 * E2) / (1 - 2 * E2))
    assert probs["under"] == pytest.approx(3 * E2 / (1 - 2 * E2))
    assert probs["over"] + probs["under"] == pytest.approx(1.0)


def test_probabilities_always_lie_in_zero_one():
    for lam in (0.3, 1.0, 4.5, 9.0, 20.0):
        for line in (0.5, 3.0, 8.5, 9.0, 21.5):
            probs = poisson.over_under_probs(line, lam)
            assert all(-1e-12 <= p <= 1 + 1e-12 for p in probs.values())
            assert sum(probs.values()) == pytest.approx(1.0)


# ---- board legs --------------------------------------------------------------------------

def game(**overrides):
    base = {"away": "NYY", "home": "BOS", "p_home": 0.6, "p_away": 0.4,
            "home_ml": -150, "away_ml": 130, "home_ml_ev": 0.02, "away_ml_ev": -0.1}
    return base | overrides


def test_a_live_or_final_game_offers_no_legs():
    assert suggest.board_candidate_legs([game(status="Live")]) == []
    assert suggest.board_candidate_legs([game(status="Final")]) == []


def test_a_preview_or_status_less_game_offers_legs():
    assert len(suggest.board_candidate_legs([game(status="Preview")])) == 2
    assert len(suggest.board_candidate_legs([game()])) == 2


def test_a_suspect_game_is_dropped():
    assert suggest.board_candidate_legs([game(suspect=True)]) == []


def test_market_blended_probability_wins_over_the_raw_model_one():
    legs = suggest.board_candidate_legs([game(p_home_bet=0.55, p_away_bet=0.45)])
    assert [leg.model_prob for leg in legs] == [0.55, 0.45]
    assert legs[0].description == "BOS ML (NYY @ BOS)"


def test_totals_legs_appear_only_with_a_market_line_and_ev():
    assert len(suggest.board_candidate_legs([game(total_line=8.5)])) == 2   # no over_ev
    with_total = game(total_line=2.5, over_ev=0.05, under_ev=-0.1, model_total=2.0,
                      over_odds=-110, under_odds=-110)
    legs = suggest.board_candidate_legs([with_total])
    assert [leg.description for leg in legs[2:]] == ["Over 2.5 (NYY @ BOS)",
                                                     "Under 2.5 (NYY @ BOS)"]


def test_total_probabilities_fall_back_to_poisson_when_no_blend_is_attached():
    # lambda 2, line 2.5: under = P(X <= 2) = 5 e^-2 = 0.67668, over = 0.32332
    with_total = game(total_line=2.5, over_ev=0.05, under_ev=-0.1, model_total=2.0)
    over, under = suggest.board_candidate_legs([with_total])[2:]
    assert over.model_prob == pytest.approx(1 - 5 * E2)
    assert under.model_prob == pytest.approx(5 * E2)


def test_blended_total_probabilities_are_used_when_present():
    with_total = game(total_line=8.5, over_ev=0.05, under_ev=-0.1, p_over_bet=0.52,
                      p_under_bet=0.48)
    over, under = suggest.board_candidate_legs([with_total])[2:]
    assert (over.model_prob, under.model_prob) == (0.52, 0.48)


# ---- suggestions ---------------------------------------------------------------------------

def cand(key, prob, odds, name=None):
    ev = None if odds is None else prob * (suggest.american_to_decimal(odds) - 1) - (1 - prob)
    return CandidateLeg(key, name or f"{key} leg", prob, odds, ev)


def test_odds_mode_ranks_slips_by_hand_computed_ev():
    # g1 0.6 @ +100 (dec 2), g2 0.55 @ +100, g3 0.5 @ +150 (dec 2.5)
    # (g1,g3): p .30, dec 5.0 -> 0.30*4 - 0.70 = 0.500
    # (g2,g3): p .275, dec 5.0 -> 0.275*4 - 0.725 = 0.375
    # (g1,g2): p .33, dec 4.0 -> 0.33*3 - 0.67 = 0.320
    legs = [cand("g1", 0.6, 100), cand("g2", 0.55, 100), cand("g3", 0.5, 150)]
    result = suggest.suggest_parlays(legs, num_legs=2)
    assert [round(s.ev, 6) for s in result] == [0.5, 0.375, 0.32]
    assert result[0].true_prob == pytest.approx(0.30)
    assert result[0].decimal_odds == pytest.approx(5.0)


def test_legs_from_one_game_are_never_combined():
    legs = [cand("g1", 0.6, 100, "a"), cand("g1", 0.65, 100, "b")]
    assert suggest.suggest_parlays(legs, num_legs=2) == []


def test_odds_mode_returns_nothing_when_no_leg_has_an_edge():
    legs = [cand("g1", 0.4, 100), cand("g2", 0.45, 100)]
    assert suggest.suggest_parlays(legs, num_legs=2) == []


def test_min_leg_ev_filters_thin_edges():
    legs = [cand("g1", 0.6, 100), cand("g2", 0.55, 100)]          # EVs 0.2 and 0.1
    assert len(suggest.suggest_parlays(legs, num_legs=2, min_leg_ev=0.15)) == 0
    assert len(suggest.suggest_parlays(legs, num_legs=2, min_leg_ev=0.05)) == 1


def test_a_parlay_needs_at_least_two_legs():
    with pytest.raises(ValueError):
        suggest.suggest_parlays([cand("g1", 0.6, 100)], num_legs=1)


def test_confidence_mode_ranks_by_hit_probability_without_odds():
    legs = [cand("g1", 0.7, None), cand("g2", 0.6, None), cand("g3", 0.5, None)]
    result = suggest.suggest_parlays(legs, num_legs=2)
    # g3 (0.5) is under the 0.55 floor, leaving one pair: 0.7 * 0.6
    assert len(result) == 1
    assert result[0].true_prob == pytest.approx(0.42)
    assert result[0].decimal_odds is None and result[0].ev is None


def test_confidence_mode_floor_is_adjustable():
    legs = [cand("g1", 0.7, None), cand("g2", 0.6, None), cand("g3", 0.5, None)]
    result = suggest.suggest_parlays(legs, num_legs=2, min_confidence_prob=0.45)
    assert [round(s.true_prob, 4) for s in result] == [0.42, 0.35, 0.3]


def test_no_leg_appears_in_more_than_the_reuse_cap_of_suggestions():
    legs = [cand(f"g{i}", 0.6 - 0.02 * i, 100) for i in range(5)]
    result = suggest.suggest_parlays(legs, num_legs=2, top_n=10)
    counts = {}
    for slip in result:
        for chosen in slip.legs:
            counts[chosen.description] = counts.get(chosen.description, 0) + 1
    assert max(counts.values()) <= suggest.MAX_LEG_REUSE
    # the very best pair (g0, g1) always leads
    assert {chosen.game_key for chosen in result[0].legs} == {"g0", "g1"}


def test_top_n_limits_the_list():
    legs = [cand(f"g{i}", 0.6, 100) for i in range(6)]
    assert len(suggest.suggest_parlays(legs, num_legs=2, top_n=2)) == 2


def test_only_the_twelve_best_legs_are_searched():
    legs = [cand(f"g{i}", 0.6 + 0.01 * i, 100) for i in range(15)]
    pool = suggest._build_pool(legs, True, 0.0, 0.55)
    assert len(pool) == suggest.MAX_LEG_POOL
    assert pool[0].game_key == "g14"          # best EV first
    assert "g0" not in {leg.game_key for leg in pool}
