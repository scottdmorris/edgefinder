"""Closing-line value against the fair (no-vig) close: the bet's payout times the market's
margin-free closing chance of that side, minus 1. Positive means the price taken beat where
the market finished, after removing the book's cut, which is the test that predicts profit."""

import datetime as dt

import pandas as pd
import pytest

from edgefinder.betting.odds_math import american_to_decimal, devig_two_way, implied_prob
from edgefinder.tracking import closing, gap_log, nba_paper
from test_kalshi_closing import closing as kalshi_close, pick, settle as settle_kalshi

LATE = "2026-11-04T23:45:00+00:00"


def fair(over, under):
    return devig_two_way(implied_prob(over), implied_prob(under))[0]


def snap(player="A", line=24.5, over=-125, under=105, event="e1", book=None):
    row = {"fetched_at": LATE, "phase": "late", "event_id": event, "player": player,
           "line": line, "over_odds": over, "under_odds": under,
           "commence_time": "2026-11-05T00:00:00Z"}
    return row | ({"book": book} if book else {})


def frame(*rows):
    return pd.DataFrame(list(rows))


# ---- the fair close ------------------------------------------------------------------------------

def test_the_fair_close_averages_every_book_that_closed_on_the_same_number():
    fanduel = frame(snap(over=-125, under=105))
    draftkings = frame(snap(over=-140, under=115, book="draftkings"))
    found = closing.fair_closes(fanduel, draftkings)
    assert found[("e1", "A", "points", 24.5)] == pytest.approx((fair(-125, 105) + fair(-140, 115)) / 2)


def test_a_book_that_closed_on_another_number_is_left_out():
    fanduel = frame(snap(over=-125, under=105))
    draftkings = frame(snap(line=25.5, over=-110, under=-110, book="draftkings"))
    assert closing.fair_closes(fanduel, draftkings)[("e1", "A", "points", 24.5)] == pytest.approx(fair(-125, 105))


def test_only_the_latest_closing_price_counts_and_early_snapshots_never_do():
    rows = frame(snap(over=-110, under=-110) | {"fetched_at": "2026-11-04T23:00:00+00:00"},
                 snap(over=-150, under=125), snap(over=200, under=-250) | {"phase": "early"})
    assert closing.fair_closes(rows)[("e1", "A", "points", 24.5)] == pytest.approx(fair(-150, 125))


def test_clv_is_the_payout_times_the_fair_chance_minus_one():
    assert closing.novig_clv_pct(True, 100, 0.55) == pytest.approx(10.0)
    assert closing.novig_clv_pct(False, 100, 0.55) == pytest.approx(-10.0)
    assert pd.isna(closing.novig_clv_pct(True, 100, float("nan")))


# ---- the picks ledger ---------------------------------------------------------------------------

def fanduel_pick(side="over", odds=-110, line=24.5):
    return {c: None for c in nba_paper.COLUMNS} | {
        "game_date": "2026-11-04", "event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
        "player": "A", "player_id": 1, "line": line, "over_odds": -110, "under_odds": -110,
        "model_version": "ewma-v1", "status": "pending", "stat": "points", "book": "fanduel",
        "pick_side": side, "pick_odds": odds}


GAMES = pd.DataFrame({"player_id": [1], "game_date": pd.to_datetime(["2026-11-04"]), "pts": [30.0]})
TODAY = dt.date(2026, 11, 6)


def settle(rows, fanduel, draftkings=None):
    ledger = pd.DataFrame(rows, columns=nba_paper.COLUMNS)
    return nba_paper.settle(ledger, GAMES, fanduel, TODAY, book_snapshots=draftkings)


def test_a_fanduel_pick_is_graded_against_the_fair_close_of_both_books():
    out = settle([fanduel_pick()], frame(snap(over=-125, under=105)),
                 frame(snap(over=-140, under=115, book="draftkings")))
    expected = (american_to_decimal(-110) * (fair(-125, 105) + fair(-140, 115)) / 2 - 1) * 100
    assert out.loc[0, "clv_novig_pct"] == pytest.approx(expected)


def test_an_under_is_graded_on_the_fair_chance_of_the_under():
    out = settle([fanduel_pick(side="under", odds=-110)], frame(snap(over=-125, under=105)))
    expected = (american_to_decimal(-110) * (1 - fair(-125, 105)) - 1) * 100
    assert out.loc[0, "clv_novig_pct"] == pytest.approx(expected)


def test_a_moved_line_or_a_row_that_was_not_a_pick_has_no_fair_close_value():
    moved = settle([fanduel_pick(line=23.5)], frame(snap(line=24.5)))
    assert pd.isna(moved.loc[0, "clv_novig_pct"])
    not_a_pick = settle([fanduel_pick(side=None, odds=None)], frame(snap()))
    assert pd.isna(not_a_pick.loc[0, "clv_novig_pct"])


def test_a_kalshi_pick_is_graded_against_kalshis_own_fair_close():
    out = settle_kalshi([pick(side="over", pick_odds=100)], kalshi_close(over_odds=-150, under_odds=130))
    assert out.loc[0, "clv_novig_pct"] == pytest.approx((2.0 * fair(-150, 130) - 1) * 100)


def test_the_summary_reports_the_average_and_how_often_the_fair_close_was_beaten():
    ledger = pd.DataFrame([fanduel_pick() | {"status": "settled", "result": "win", "pnl_units": 0.9,
                                             "clv_novig_pct": 4.0},
                           fanduel_pick() | {"status": "settled", "result": "loss", "pnl_units": -1.0,
                                             "clv_novig_pct": -2.0, "player": "B"}],
                          columns=nba_paper.COLUMNS)
    facts = nba_paper.summary(ledger)
    assert facts["avg_clv_novig_pct"] == pytest.approx(1.0)
    assert facts["beat_fair_close_pct"] == pytest.approx(50.0)
    assert facts["clv_novig_n"] == 2


# ---- the gap logs ---------------------------------------------------------------------------------

def gap(side="Over", line=24.5, odds=100, player="A"):
    return {c: None for c in gap_log.COLUMNS} | {
        "game_date": "2026-11-04", "event_id": "e1", "player": player, "player_id": 1,
        "side": side, "line": line, "odds": odds, "book": "fanduel", "status": "settled"}


def test_gap_bets_on_a_main_line_get_a_fair_close_value_and_x_plus_bets_do_not():
    log = pd.DataFrame([gap(), gap(side="15+", line=14.5)], columns=gap_log.COLUMNS)
    out = gap_log.attach_closing(log, frame(snap(over=-125, under=105)))
    assert out.loc[0, "clv_novig_pct"] == pytest.approx((2.0 * fair(-125, 105) - 1) * 100)
    assert pd.isna(out.loc[1, "clv_novig_pct"])


def test_the_gap_summary_reports_the_fair_close_value():
    log = pd.DataFrame([gap() | {"result": "win", "pnl_units": 1.0, "clv_novig_pct": 3.0, "how": "exact"}],
                       columns=gap_log.COLUMNS)
    assert gap_log.summary(log)["all"]["avg_clv_novig_pct"] == pytest.approx(3.0)


def test_a_log_written_before_the_new_column_is_upgraded_before_rows_are_added(tmp_path):
    path = tmp_path / "gaps.csv"
    old_columns = [c for c in gap_log.COLUMNS if c != "clv_novig_pct"]
    pd.DataFrame([{c: gap()[c] for c in old_columns}], columns=old_columns).to_csv(path, index=False)
    gap_log.append([gap(player="B") | {"player_id": 2, "status": "pending"}], path)
    saved = gap_log.load(path)
    assert list(saved.columns) == gap_log.COLUMNS and list(saved["player"]) == ["A", "B"]


@pytest.mark.parametrize("stamp", ["2026-11-05T00:00:00Z", "2026-11-05T00:05:00Z"])
def test_prices_at_or_after_tip_cannot_replace_the_pregame_close(stamp):
    rows = frame(snap(over=-110, under=-110), snap(over=-900, under=600) | {"fetched_at": stamp})
    assert closing.fair_closes(rows)[("e1", "A", "points", 24.5)] == pytest.approx(.5)
    out = settle([fanduel_pick()], rows)
    assert out.loc[0, "closing_over_odds"] == -110
    assert out.loc[0, "clv_novig_pct"] == pytest.approx((american_to_decimal(-110) * .5 - 1) * 100)


def test_unknown_or_invalid_timestamps_do_not_establish_a_close():
    for overrides in ({"commence_time": None}, {"commence_time": "bad"}, {"fetched_at": "bad"}):
        assert closing.fair_closes(frame(snap() | overrides)) == {}


def test_kalshi_uses_ledger_tip_when_snapshot_has_none():
    out = settle_kalshi([pick()], kalshi_close(fetched_at="2026-11-05T00:05:00Z"))
    assert pd.isna(out.loc[0, "clv_novig_pct"])
    assert pd.isna(out.loc[0, "closing_over_odds"])


def test_recalculation_clears_a_previously_saved_invalid_fair_close():
    out = settle([fanduel_pick() | {"clv_novig_pct": 25.0}],
                 frame(snap() | {"fetched_at": "2026-11-05T00:05:00Z"}))
    assert pd.isna(out.loc[0, "clv_novig_pct"])


def test_record_api_uses_fair_close_and_does_not_fall_back_to_old_metric():
    from edgefinder.api import record
    ledger = pd.DataFrame([fanduel_pick() | {"status": "settled", "result": "win", "pnl_units": .9,
                                             "clv_pct": 15.0, "clv_novig_pct": -5.0}],
                          columns=nba_paper.COLUMNS)
    [facts] = record._clv(ledger)
    assert facts["avg_pct"] == -5.0 and facts["beat_pct"] == 0 and facts["measured"] == 1
    ledger["clv_novig_pct"] = None
    assert record._clv(ledger) == []
