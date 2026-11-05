"""Hand-verified checks on slip building: leg probabilities, EV, stake math,
and the plain-language formatting of money and chances."""

import numpy as np
import pandas as pd
import pytest

from edgefinder.tracking import nba_alt, nba_paper, nba_parlay

DAY = "2026-11-04"
BASE_LEDGER = dict(
    game_date=DAY, event_id="e1", home="Detroit Pistons", away="Philadelphia 76ers",
    player="Cade Cunningham", player_id=1, line=24.5, over_odds=-110, under_odds=-110,
    model_version="ewma-v1", model_p_over=0.7, fair_p_over=0.5)


def ledger(*rows):
    return pd.DataFrame([BASE_LEDGER | r for r in rows])


def alt_ledger(*rows):
    base = dict(game_date=DAY, event_id="e1", home="Detroit Pistons", away="Philadelphia 76ers",
                player="Cade Cunningham", player_id=1, threshold=25, over_odds=150,
                model_version="ewma-v1", model_p=0.5, market_p=0.4)
    return pd.DataFrame([base | r for r in rows])


NO_ALT = pd.DataFrame(columns=nba_alt.COLUMNS)


# ---- formatting ---------------------------------------------------------------------------

@pytest.mark.parametrize("amount, text", [
    (12.5, "$12.50"), (0, "$0.00"), (1234567.891, "$1,234,567.89"), (-3, "-$3.00")])
def test_money_plain(amount, text):
    assert nba_parlay.money(amount) == text


@pytest.mark.parametrize("amount, text", [(12.5, "+$12.50"), (-3, "-$3.00"), (0, "$0.00")])
def test_money_signed(amount, text):
    assert nba_parlay.money(amount, signed=True) == text


def test_money_never_shows_negative_zero():
    assert nba_parlay.money(-0.004) == "$0.00"


@pytest.mark.parametrize("probability, text", [
    (0.0, "never"), (-0.2, "never"),
    (0.027, "1 in 37"),          # 1/0.027 = 37.04
    (0.5, "1 in 2"),
    (0.25, "1 in 4"),
    (0.0001, "1 in 10,000"),
    (0.6, "6 in 10"),            # from 60% up it reads as N in 10
    (0.89, "9 in 10"),
])
def test_one_in_hand_values(probability, text):
    assert nba_parlay.one_in(probability) == text


def test_a_tiny_chance_never_reads_as_one_in_zero():
    assert nba_parlay.one_in(0.9999 * 1e-9).startswith("1 in")


def test_a_likely_but_not_certain_chance_never_reads_as_ten_in_ten():
    assert nba_parlay.one_in(0.96) != "10 in 10"


def test_verdict_wins_loses_and_break_even_boundaries():
    assert "wins about 12 cents" in nba_parlay.verdict(0.12)
    assert "loses about 20 cents" in nba_parlay.verdict(-0.20)
    assert "hasn't been tested" in nba_parlay.verdict(0.12)
    # exactly 5 cents either way is still 'about even'
    assert "break-even" in nba_parlay.verdict(0.05)
    assert "break-even" in nba_parlay.verdict(-0.05)
    assert "break-even" in nba_parlay.verdict(0.0)
    assert "wins" in nba_parlay.verdict(0.0501)
    assert "loses" in nba_parlay.verdict(-0.0501)


def test_headshot_url_accepts_numpy_and_string_ids():
    expected = "https://cdn.nba.com/headshots/nba/latest/260x190/1629029.png"
    assert nba_parlay.headshot_url(1629029) == expected
    assert nba_parlay.headshot_url(np.int64(1629029)) == expected
    assert nba_parlay.headshot_url("1629029") == expected


def test_model_names_translate_and_unknown_versions_pass_through():
    assert nba_parlay.model_name("ewma-v1") == "Simple: recent scoring average"
    assert nba_parlay.model_name("future-v9") == "future-v9"


# ---- stake outcomes ----------------------------------------------------------------------------------

def test_stake_outcomes_by_hand():
    # $10 at decimal 3.5, +10% EV: back $35, profit $25, lose $10, expect +$1
    out = nba_parlay.stake_outcomes(10.0, 3.5, 0.10)
    assert out == {"total_return": 35.0, "profit_if_wins": 25.0, "loss_if_misses": -10.0,
                   "expected_profit": 1.0}


def test_a_zero_stake_is_all_zeros():
    out = nba_parlay.stake_outcomes(0.0, 4.0, 0.2)
    assert all(value == 0 for value in out.values())


def test_return_minus_stake_is_the_profit():
    out = nba_parlay.stake_outcomes(7.5, 2.2, -0.04)
    assert out["total_return"] - 7.5 == pytest.approx(out["profit_if_wins"])
    assert out["expected_profit"] == pytest.approx(-0.3)


def test_a_negative_stake_is_rejected():
    with pytest.raises(ValueError):
        nba_parlay.stake_outcomes(-1.0, 2.0, 0.0)


# ---- slip toggling ---------------------------------------------------------------------------------------

PLAYERS = ["a", "b", "a", "c"]


def test_tapping_a_price_adds_it_and_tapping_again_removes_it():
    slip = nba_parlay.toggle_leg([], 0, PLAYERS)
    assert slip == [0]
    assert nba_parlay.toggle_leg(slip, 0, PLAYERS) == []


def test_a_second_price_for_the_same_player_replaces_the_first():
    assert nba_parlay.toggle_leg([0, 1], 2, PLAYERS) == [1, 2]


def test_toggling_does_not_mutate_the_slip():
    slip = [0, 1]
    nba_parlay.toggle_leg(slip, 3, PLAYERS)
    nba_parlay.toggle_leg(slip, 1, PLAYERS)
    assert slip == [0, 1]


def test_a_slip_never_holds_a_player_twice():
    slip = []
    for index in (0, 1, 2, 3, 0, 2):
        slip = nba_parlay.toggle_leg(slip, index, PLAYERS)
        assert len({PLAYERS[i] for i in slip}) == len(slip)


# ---- teams -------------------------------------------------------------------------------------------------

def test_player_teams_use_the_most_recent_game():
    games = pd.DataFrame({
        "player_id": [1, 1, 2], "team": ["OLD", "NEW", "BOS"],
        "game_date": pd.to_datetime(["2026-01-01", "2026-03-01", "2026-02-01"])})
    assert nba_parlay.player_teams(games) == {1: "NEW", 2: "BOS"}


# ---- candidate legs --------------------------------------------------------------------------------------------

def test_over_and_under_blend_toward_the_market_by_hand():
    # over: 0.3*0.7 + 0.7*0.5 = 0.56 ; under: 0.3*0.3 + 0.7*0.5 = 0.44
    table = nba_parlay.candidate_legs(ledger({}), NO_ALT, DAY, "ewma-v1")
    over = table[table["Side"] == "Over"].iloc[0]
    under = table[table["Side"] == "Under"].iloc[0]
    assert over["prob"] == pytest.approx(0.56) and under["prob"] == pytest.approx(0.44)
    assert over["Blended %"] == pytest.approx(56.0)
    assert over["Model %"] == pytest.approx(70.0) and over["Market %"] == pytest.approx(50.0)
    assert over["Leg"] == "Cade Cunningham · Over 24.5 points"
    assert over["Game"] == "Philadelphia 76ers @ Detroit Pistons"
    assert (over["away_abbr"], over["home_abbr"]) == ("PHI", "DET")


def test_over_and_under_blended_chances_sum_to_one():
    for model_p, fair_p in [(0.7, 0.5), (0.2, 0.65), (0.5, 0.5), (0.95, 0.4)]:
        table = nba_parlay.candidate_legs(
            ledger({"model_p_over": model_p, "fair_p_over": fair_p}), NO_ALT, DAY, "ewma-v1")
        assert table["prob"].sum() == pytest.approx(1.0)
        assert table["prob"].between(0.0, 1.0).all()


def test_leg_ev_percent_by_hand():
    # over blend 0.56 at -110 (21/11): 0.56*(10/11) - 0.44 = 0.069091 -> 6.9091%
    table = nba_parlay.candidate_legs(ledger({}), NO_ALT, DAY, "ewma-v1")
    over = table[table["Side"] == "Over"].iloc[0]
    assert over["Leg EV %"] == pytest.approx((0.56 * 10 / 11 - 0.44) * 100.0)
    # under blend 0.44 at -110: 0.44*(10/11) - 0.56 = -0.16
    under = table[table["Side"] == "Under"].iloc[0]
    assert under["Leg EV %"] == pytest.approx((0.44 * 10 / 11 - 0.56) * 100.0)


def test_x_plus_legs_blend_and_use_half_point_lines():
    # model 0.5, market 0.4 -> blend 0.3*0.5 + 0.7*0.4 = 0.43 ; at +150: 0.43*1.5 - 0.57 = 0.075
    table = nba_parlay.candidate_legs(ledger({}), alt_ledger({}), DAY, "ewma-v1")
    x_plus = table[table["Side"] == "25+"].iloc[0]
    assert x_plus["prob"] == pytest.approx(0.43)
    assert x_plus["Leg EV %"] == pytest.approx(7.5)
    assert bool(x_plus["is_over"]) is True and x_plus["line"] == 24.5
    assert x_plus["Leg"] == "Cade Cunningham · 25+ points"


def test_other_dates_and_models_are_left_out():
    rows = [{}, {"game_date": "2026-11-05"}, {"model_version": "minutes-v1"}]
    table = nba_parlay.candidate_legs(ledger(*rows), NO_ALT, DAY, "ewma-v1")
    assert len(table) == 2
    other = nba_parlay.candidate_legs(ledger(*rows), NO_ALT, "2026-11-05", "ewma-v1")
    assert len(other) == 2


def test_nothing_priced_gives_an_empty_table_with_the_right_columns():
    table = nba_parlay.candidate_legs(ledger({}), NO_ALT, "2030-01-01", "ewma-v1")
    assert table.empty and list(table.columns) == nba_parlay.COLUMNS


# ---- turning picks into builder legs ---------------------------------------------------------------------------------

def test_to_legs_carries_over_flag_probability_and_price():
    table = nba_parlay.candidate_legs(ledger({}), NO_ALT, DAY, "ewma-v1")
    legs = nba_parlay.to_legs(table, {1: "DET"})
    by_side = {leg.label.split(" · ")[1]: leg for leg in legs}
    over, under = by_side["Over 24.5 points"], by_side["Under 24.5 points"]
    assert over.is_over is True and under.is_over is False
    assert over.prob == pytest.approx(0.56) and over.american_odds == -110.0
    assert over.team == "DET"


def test_an_unknown_team_is_not_confused_with_anyone_elses():
    table = nba_parlay.candidate_legs(
        ledger({}, {"player": "Other", "player_id": 2}), NO_ALT, DAY, "ewma-v1")
    legs = nba_parlay.to_legs(table, {})
    assert {leg.team for leg in legs} == {"?1", "?2"}


# ---- suggestions -----------------------------------------------------------------------------------------------------------

def good_game(event, player_id, name):
    """One game with a single worthwhile leg: the over, 62% model vs 50% market at +100.
    Blend 0.3*0.62 + 0.7*0.5 = 0.536 ; EV = 0.536*1 - 0.464 = 0.072 (7.2%).
    The under (-120, blend 0.464) loses money and is filtered out."""
    return {"event_id": event, "player_id": player_id, "player": name, "over_odds": 100,
            "under_odds": -120, "model_p_over": 0.62, "fair_p_over": 0.5}


def two_good_games():
    return nba_parlay.candidate_legs(
        ledger(good_game("e1", 1, "A"), good_game("e2", 2, "B")), NO_ALT, DAY, "ewma-v1")


def test_a_two_game_slip_is_priced_by_hand():
    # chance 0.536^2 = 0.287296 ; pays 2*2 - 1 = 3 ; EV = 0.287296*3 - 0.712704 = 0.149184
    slips = nba_parlay.suggest_parlays(two_good_games())
    assert len(slips) == 1
    best = slips.iloc[0]
    assert best["Legs"] == 2
    assert best["Chance %"] == pytest.approx(28.7296)
    assert best["Pays"] == pytest.approx(3.0)
    assert best["EV %"] == pytest.approx(14.9184)
    assert "A · Over 24.5 points" in best["Slip"] and "B · Over 24.5 points" in best["Slip"]


def test_the_slip_chance_never_exceeds_the_weakest_leg():
    slips = nba_parlay.suggest_parlays(two_good_games())
    assert (slips["Chance %"] <= 53.6 + 1e-9).all()


def test_a_cautious_style_drops_slips_that_are_too_unlikely():
    # 28.7% is below the 35% 'Safer' bar but above the 20% 'Balanced' and 8% 'Bigger' bars
    candidates = two_good_games()
    assert nba_parlay.suggest_parlays(candidates, min_chance=nba_parlay.STYLES["Safer"]).empty
    assert len(nba_parlay.suggest_parlays(candidates, min_chance=nba_parlay.STYLES["Bigger payouts"])) == 1


def test_empty_suggestions_have_the_documented_columns():
    slips = nba_parlay.suggest_parlays(two_good_games(), min_chance=0.9)
    assert list(slips.columns) == ["Slip", "Legs", "Chance %", "Pays", "EV %", "bets"]


def test_one_game_cannot_make_a_slip():
    only_one = nba_parlay.candidate_legs(ledger(good_game("e1", 1, "A")), NO_ALT, DAY, "ewma-v1")
    assert nba_parlay.suggest_parlays(only_one).empty


def test_two_players_in_one_game_are_never_combined():
    same_game = nba_parlay.candidate_legs(
        ledger(good_game("e1", 1, "A"), good_game("e1", 2, "B")), NO_ALT, DAY, "ewma-v1")
    assert nba_parlay.suggest_parlays(same_game).empty


def test_legs_with_no_edge_are_not_offered():
    # model == market: blend equals market, EV is the negative vig
    flat = {"model_p_over": 0.5, "fair_p_over": 0.5, "over_odds": -110, "under_odds": -110}
    candidates = nba_parlay.candidate_legs(
        ledger({"event_id": "e1"} | flat, {"event_id": "e2", "player_id": 2, "player": "B"} | flat),
        NO_ALT, DAY, "ewma-v1")
    assert nba_parlay.suggest_parlays(candidates).empty


def test_a_model_far_from_the_market_is_treated_as_a_data_problem():
    wild = good_game("e1", 1, "A") | {"model_p_over": 0.80}      # 30 points from the market
    other = good_game("e2", 2, "B")
    candidates = nba_parlay.candidate_legs(ledger(wild, other), NO_ALT, DAY, "ewma-v1")
    assert nba_parlay.suggest_parlays(candidates).empty


def test_a_near_certain_leg_that_pays_nothing_is_not_offered():
    # -1500 pays decimal 1.0667, below the 1.30 floor
    chalk = good_game("e1", 1, "A") | {"over_odds": -1500, "model_p_over": 0.97,
                                        "fair_p_over": 0.95}
    other = good_game("e2", 2, "B")
    candidates = nba_parlay.candidate_legs(ledger(chalk, other), NO_ALT, DAY, "ewma-v1")
    assert nba_parlay.suggest_parlays(candidates).empty


def test_slip_positions_point_back_into_the_candidates():
    candidates = two_good_games()
    slip = nba_parlay.suggest_parlays(candidates).iloc[0]
    assert sorted(candidates.loc[slip["bets"], "Player"]) == ["A", "B"]


def test_three_leg_slips_are_searched_up_to_max_legs():
    rows = [good_game(f"e{i}", i, f"P{i}") for i in range(1, 4)]
    candidates = nba_parlay.candidate_legs(ledger(*rows), NO_ALT, DAY, "ewma-v1")
    slips = nba_parlay.suggest_parlays(candidates, max_legs=3, min_chance=0.1, top=10)
    assert set(slips["Legs"]) == {2, 3}
    triple = slips[slips["Legs"] == 3].iloc[0]
    assert triple["Chance %"] == pytest.approx(0.536 ** 3 * 100.0)       # 15.40
    assert triple["Pays"] == pytest.approx(7.0)                          # 2*2*2 - 1
    assert list(slips["EV %"]) == sorted(slips["EV %"], reverse=True)


def test_top_limits_the_number_of_slips():
    rows = [good_game(f"e{i}", i, f"P{i}") for i in range(1, 5)]
    candidates = nba_parlay.candidate_legs(ledger(*rows), NO_ALT, DAY, "ewma-v1")
    assert len(nba_parlay.suggest_parlays(candidates, top=2, min_chance=0.1)) == 2


def test_model_weight_matches_the_paper_ledger():
    assert nba_paper.MODEL_WEIGHT == 0.30 and nba_alt.MIN_MODEL_P == 0.35


def test_two_legs_from_one_game_are_never_put_on_the_same_slip():
    # Game e1 offers two worthwhile X+ rungs: 25+ (best value) and 15+ (likeliest).
    #   25+: model 0.5, market 0.4 @ +150 -> blend 0.43, EV 7.5%
    #   15+: model 0.75, market 0.6667 @ -200 -> blend 0.69167, EV 0.69167*0.5 - 0.30833 = 4.58%
    # Game e2 offers one over (blend 0.536, +100). Both e1 legs are in the search pool, but
    # only one of them may be paired with e2's.
    x_plus = alt_ledger(
        {"event_id": "e1", "threshold": 25, "over_odds": 150, "model_p": 0.5, "market_p": 0.4},
        {"event_id": "e1", "threshold": 15, "over_odds": -200, "model_p": 0.75,
         "market_p": 0.6667})
    candidates = nba_parlay.candidate_legs(
        ledger(good_game("e2", 2, "B")), x_plus, DAY, "ewma-v1")
    slips = nba_parlay.suggest_parlays(candidates, min_chance=0.1)
    assert len(slips) == 2
    for slip in slips["Slip"]:
        assert ("25+" in slip) != ("15+" in slip)       # exactly one of the two e1 legs
        assert "B · Over 24.5 points" in slip
    # 25+ slip: 0.43*0.536 = 0.23048 ; 15+ slip: 0.69167*0.536 = 0.37073
    assert sorted(slips["Chance %"]) == pytest.approx([23.048, 37.073], abs=0.01)
