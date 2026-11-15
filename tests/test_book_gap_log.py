"""FanDuel-vs-DraftKings disagreements, logged as bets at the early snapshot and graded like
the Kalshi gaps, so the flag can be judged on results instead of on how it looks."""

import datetime as dt

import pandas as pd
import pytest

from edgefinder.tracking import book_gaps, gap_log

EVENT = {"event_id": "e1", "commence_time": "2026-11-06T00:00:00Z",
         "home": "Golden State Warriors", "away": "Miami Heat"}
BEFORE = dt.datetime(2026, 11, 5, 20, 0, tzinfo=dt.timezone.utc)
AFTER = dt.datetime(2026, 11, 6, 0, 5, tzinfo=dt.timezone.utc)
IDS = {"A": 1, "B": 2, "C": 3}


def line(player, number, over, under):
    return {"player": player, "line": number, "over_odds": over, "under_odds": under}


FANDUEL = [line("A", 20.5, 100, -120),      # DraftKings says the over is ~57%: FanDuel pays 2.0
           line("B", 9.5, -110, -110),      # same prices: nothing
           line("C", 14.5, -110, -110)]     # FanDuel's number is a point lower: its over is easier
DRAFTKINGS = [line("A", 20.5, -150, 120), line("B", 9.5, -110, -110),
              line("C", 15.5, -110, -110)]


def logged(now=BEFORE, fanduel=FANDUEL, ids=IDS):
    rows = book_gaps.rows_to_log(EVENT, fanduel, DRAFTKINGS, ids, now, "2026-11-05")
    return {row["player"]: row for row in rows}


def test_a_better_price_on_the_same_number_is_logged_as_a_fanduel_bet():
    row = logged()["A"]
    fair_over = 0.6 / (0.6 + 100 / 220)
    assert (row["side"], row["line"], row["odds"], row["book"]) == ("Over", 20.5, 100.0, "fanduel")
    assert row["how"] == "price" and row["reference"] == "DraftKings"
    assert row["reference_p"] == pytest.approx(fair_over, abs=1e-6)
    assert row["edge_pct"] == pytest.approx((fair_over * 2.0 - 1.0) * 100, abs=1e-3)
    assert row["player_id"] == 1 and row["status"] == "pending"
    assert set(row) == set(gap_log.COLUMNS)


def test_a_lower_number_at_fanduel_is_logged_as_its_over_and_a_higher_one_as_its_under():
    over = logged()["C"]
    assert (over["side"], over["line"], over["how"]) == ("Over", 14.5, "number")
    higher = [line("C", 16.5, -110, -110)]
    under = logged(fanduel=higher)["C"]
    assert (under["side"], under["line"], under["odds"]) == ("Under", 16.5, -110.0)


def test_nothing_worth_a_look_is_not_logged():
    assert "B" not in logged()


def test_nothing_is_logged_once_the_game_has_started():
    assert logged(now=AFTER) == {}


def test_a_player_the_ledger_cannot_identify_is_skipped_not_guessed():
    assert "A" not in logged(ids={"C": 3})


def test_logged_gaps_are_graded_with_the_same_rules_as_the_kalshi_gaps(tmp_path):
    path = tmp_path / "book_gaps.csv"
    rows = book_gaps.rows_to_log(EVENT, FANDUEL, DRAFTKINGS, IDS, BEFORE, "2026-11-05")
    assert gap_log.append(rows, path) == 2
    assert gap_log.append(rows, path) == 0                    # the first call stands
    games = pd.DataFrame({"player_id": [1, 3], "game_date": pd.to_datetime(["2026-11-05"] * 2),
                          "pts": [25.0, 12.0]})
    out = gap_log.settle(gap_log.load(path), games, dt.date(2026, 11, 6)).set_index("player")
    assert out.loc["A", "result"] == "win" and out.loc["A", "pnl_units"] == pytest.approx(1.0)
    assert out.loc["C", "result"] == "loss" and out.loc["C", "pnl_units"] == -1.0


def test_the_summary_splits_better_prices_from_different_numbers(tmp_path):
    path = tmp_path / "book_gaps.csv"
    gap_log.append(book_gaps.rows_to_log(EVENT, FANDUEL, DRAFTKINGS, IDS, BEFORE, "2026-11-05"), path)
    s = gap_log.summary(gap_log.load(path), splits=book_gaps.HOW)
    assert s["all"]["logged"] == 2 and s["price"]["logged"] == 1 and s["number"]["logged"] == 1
