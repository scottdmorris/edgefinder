"""Kalshi ladder picks must pass the same guardrails as X+ picks: a long shot the model barely
believes in, or a price the model wildly disagrees with, is not a pick there."""

from edgefinder.tracking import nba_paper

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
WHEN, DAY = "2026-11-04T17:00:00+00:00", "2026-11-04"


def row(mean, point, over, under, book):
    lines = [{"player": "Cade", "line": point, "over_odds": over, "under_odds": under}]
    return nba_paper.build_ledger_rows(EVENT, lines, {"Cade": {"player_id": 1, "mean": mean}},
                                       WHEN, DAY, book=book)[0]


def test_a_kalshi_long_shot_the_model_gives_under_35_percent_is_not_a_pick():
    # 31+ for a 26-point scorer at +450: the model likes the price but rates it ~30%
    kalshi = row(26.0, 30.5, 450, -700, "kalshi")
    assert kalshi["model_p_over"] < nba_paper.MIN_MODEL_P
    assert kalshi["pick_side"] is None


def test_the_same_long_shot_on_fanduel_is_still_judged_on_value_alone():
    fanduel = row(26.0, 30.5, 450, -700, "fanduel")
    assert fanduel["pick_side"] == "over"


def test_a_kalshi_price_the_model_disagrees_with_by_more_than_15_points_is_not_a_pick():
    # the market says ~45% over, the model says ~64%: a data problem, not free money
    kalshi = row(30.0, 24.5, 110, -140, "kalshi")
    gap = abs(kalshi["model_p_over"] - kalshi["fair_p_over"])
    assert gap > nba_paper.MAX_DISAGREEMENT
    assert kalshi["pick_side"] is None


def test_a_kalshi_pick_near_the_market_and_likely_enough_is_still_a_pick():
    kalshi = row(28.0, 24.5, 120, -150, "kalshi")
    assert kalshi["pick_side"] == "over"


def test_an_under_pick_is_checked_on_the_under_s_own_chance():
    kalshi = row(23.0, 24.5, -120, 100, "kalshi")
    assert kalshi["pick_side"] == "under"
    assert 1 - kalshi["model_p_over"] >= nba_paper.MIN_MODEL_P
