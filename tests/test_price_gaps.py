import pandas as pd
import pytest

from edgefinder.betting import negbin
from edgefinder.models import nba_context_v2
from edgefinder.tracking import nba_alt, nba_paper
from edgefinder.tracking import price_gaps as pg

DAY = "2026-11-05"
T = "2026-11-05T23:30:00+00:00"


def line(book, line=24.5, over=-110, under=-110, fair=0.5, recorded=T, player="A", pid=1):
    base = {c: None for c in nba_paper.COLUMNS}
    return base | {"game_date": DAY, "event_id": "e1", "away": "Miami Heat",
                   "home": "Golden State Warriors", "player": player, "player_id": pid,
                   "line": line, "over_odds": over, "under_odds": under, "fair_p_over": fair,
                   "recorded_at": recorded, "stat": "points", "book": book,
                   "model_version": "ewma-v1"}


def ledger(*rows):
    return pd.DataFrame(list(rows), columns=nba_paper.COLUMNS)


def alt(threshold=25, over=100, recorded=T, pid=1):
    base = {c: None for c in nba_alt.COLUMNS}
    return pd.DataFrame([base | {"game_date": DAY, "event_id": "e1", "away": "Miami Heat",
                                 "home": "Golden State Warriors", "player": "A", "player_id": pid,
                                 "threshold": threshold, "over_odds": over, "recorded_at": recorded,
                                 "model_version": "ewma-v1"}], columns=nba_alt.COLUMNS)


NO_ALT = pd.DataFrame(columns=nba_alt.COLUMNS)


def test_fanduel_paying_more_than_kalshis_fair_chance_is_a_gap_worked_by_hand():
    # Kalshi says 60% for the over; FanDuel pays -110 (decimal 21/11): 0.6 * 21/11 - 1 = +14.5%
    gaps = pg.find_gaps(ledger(line("fanduel"), line("kalshi", over=-150, under=150, fair=0.6)),
                        NO_ALT, DAY)
    fd = gaps[gaps["Book"] == "fanduel"].iloc[0]
    assert (fd["Bet"], fd["Side"], fd["How"], fd["Reference"]) == ("Over 24.5", "Over", "exact",
                                                                   "Kalshi")
    assert fd["Edge %"] == pytest.approx((0.6 * 21 / 11 - 1) * 100)
    assert fd["Reference %"] == pytest.approx(60.0)
    assert fd["Price says %"] == pytest.approx(110 / 210 * 100)          # -110 implies 52.4%
    # FanDuel's under: 0.4 * 21/11 - 1 is negative, so it is not a gap
    assert not ((gaps["Book"] == "fanduel") & (gaps["Side"] == "Under")).any()


def test_the_other_way_kalshi_paying_more_than_fanduels_fair_chance_is_a_gap_too():
    # FanDuel's fair over is 50%; Kalshi's "no" at +150 (decimal 2.5) pays 0.5 * 2.5 - 1 = +25%
    gaps = pg.find_gaps(ledger(line("fanduel"), line("kalshi", over=-150, under=150, fair=0.6)),
                        NO_ALT, DAY)
    ks = gaps[gaps["Book"] == "kalshi"].iloc[0]
    assert (ks["Side"], ks["Reference"]) == ("Under", "FanDuel")
    assert ks["Edge %"] == pytest.approx(25.0)


def test_fanduels_x_plus_ladder_is_matched_to_kalshis_contract_on_the_same_number():
    # FanDuel 25+ at +100 (decimal 2.0) against Kalshi's 60% at 24.5: 0.6 * 2 - 1 = +20%
    gaps = pg.find_gaps(ledger(line("kalshi", fair=0.6)), alt(threshold=25, over=100), DAY)
    row = gaps.iloc[0]
    assert (row["Bet"], row["Side"], row["line"], row["How"]) == ("25+", "25+", 24.5, "exact")
    assert row["Edge %"] == pytest.approx(20.0)


def test_small_gaps_and_implausibly_large_ones_are_left_out():
    small = pg.find_gaps(ledger(line("kalshi", fair=0.51)), alt(over=100), DAY)   # +2%
    assert small.empty
    huge = pg.find_gaps(ledger(line("kalshi", fair=0.6)), alt(over=150), DAY)      # +50%: stale
    assert huge.empty


def test_prices_recorded_far_apart_in_time_are_not_compared():
    later = "2026-11-06T02:00:00+00:00"                                              # 2.5 h later
    assert pg.find_gaps(ledger(line("kalshi", fair=0.6, recorded=later)), alt(), DAY).empty


def test_a_ladder_of_kalshi_prices_is_turned_back_into_the_projection_that_made_it():
    width = nba_context_v2.MODEL_DISPERSION
    ladder = [(n - 0.5, float(negbin.over_prob(n - 0.5, 20.0, width))) for n in (15, 20, 25)]
    assert pg.fit_ladder_mean(ladder) == pytest.approx(20.0, abs=0.05)
    assert pg.fit_ladder_mean(ladder[:1]) is None                                  # one point: no curve


def test_fanduels_main_line_between_kalshis_numbers_is_priced_from_the_ladder_and_labelled():
    rows = ledger(line("fanduel", line=27.5, over=120, under=-150, fair=0.43),
                  line("kalshi", line=24.5, fair=0.6), line("kalshi", line=29.5, fair=0.35))
    gaps = pg.find_gaps(rows, NO_ALT, DAY, min_edge=-1.0)                         # show everything
    est = gaps[(gaps["Book"] == "fanduel") & (gaps["Side"] == "Over")].iloc[0]
    assert est["How"] == "estimated"
    assert 35.0 < est["Reference %"] < 60.0          # between Kalshi's 30+ and 25+ chances
    assert est["Edge %"] == pytest.approx((est["Reference %"] / 100 * 2.2 - 1) * 100)   # +120 = 2.2


def test_one_kalshi_number_is_not_enough_to_estimate_a_different_line():
    rows = ledger(line("fanduel", line=27.5), line("kalshi", line=24.5, fair=0.6))
    assert pg.find_gaps(rows, NO_ALT, DAY, min_edge=-1.0).empty


def test_a_day_without_both_markets_has_no_gaps_and_keeps_the_columns():
    gaps = pg.find_gaps(ledger(line("fanduel")), NO_ALT, DAY)
    assert gaps.empty and list(gaps.columns) == pg.COLUMNS


def test_the_same_price_written_by_several_models_is_counted_once():
    rows = ledger(line("kalshi", fair=0.6), {**line("kalshi", fair=0.6), "model_version": "minutes-v1"})
    assert len(pg.find_gaps(rows, alt(), DAY)) == 1


def test_a_gap_reads_in_plain_words():
    row = {"Book": "fanduel", "Odds": 150.0, "Price says %": 40.0, "Reference %": 46.0,
           "Reference": "Kalshi", "How": "estimated"}
    assert pg.describe(row) == ("FanDuel pays +150 (40% implied); Kalshi's fair chance is 46% "
                                "(estimated from its ladder).")


def test_a_gap_is_found_in_the_parlay_builders_table_so_it_can_be_added():
    candidates = pd.DataFrame({"player_id": [1, 1], "event_id": ["e1", "e1"],
                               "Side": ["Over", "25+"], "line": [24.5, 24.5]}, index=[7, 8])
    assert pg.candidate_index(candidates, {"player_id": 1, "event_id": "e1", "Side": "25+",
                                           "line": 24.5}) == 8
    assert pg.candidate_index(candidates, {"player_id": 2, "event_id": "e1", "Side": "Over",
                                           "line": 24.5}) is None
