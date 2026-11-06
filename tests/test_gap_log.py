import datetime as dt

import pandas as pd
import pytest

from edgefinder.tracking import gap_log
from edgefinder.tracking import price_gaps as pg

TIP = "2026-11-06T00:00:00Z"
BEFORE = dt.datetime(2026, 11, 5, 20, 0, tzinfo=dt.timezone.utc)
AFTER = dt.datetime(2026, 11, 6, 0, 5, tzinfo=dt.timezone.utc)


def gaps(*rows):
    base = {"Game": "Miami Heat @ Golden State Warriors", "Player": "Klay Thompson",
            "player_id": 7, "event_id": "e1", "Bet": "15+", "Side": "15+", "line": 14.5,
            "Book": "fanduel", "Odds": 220.0, "Price says %": 31.25, "Reference %": 33.9,
            "Reference": "Kalshi", "How": "exact", "Edge %": 8.48}
    return pd.DataFrame([base | r for r in rows] or [base], columns=pg.COLUMNS)


LEDGER = pd.DataFrame({"event_id": ["e1"], "commence_time": [TIP]})


def test_a_gap_before_tip_off_is_logged_with_its_game_time_and_rounded_chances():
    [row] = gap_log.rows_to_log(gaps(), LEDGER, "2026-11-05", BEFORE)
    assert row["commence_time"] == TIP and row["game_date"] == "2026-11-05"
    assert (row["bet"], row["side"], row["line"], row["book"], row["odds"]) == (
        "15+", "15+", 14.5, "fanduel", 220.0)
    assert row["price_p"] == pytest.approx(0.3125) and row["reference_p"] == pytest.approx(0.339)
    assert row["status"] == "pending" and row["logged_at"] == BEFORE.isoformat()


def test_a_gap_is_never_logged_once_its_game_has_started_or_without_a_known_start():
    assert gap_log.rows_to_log(gaps(), LEDGER, "2026-11-05", AFTER) == []
    assert gap_log.rows_to_log(gaps({"event_id": "nope"}), LEDGER, "2026-11-05", BEFORE) == []


def test_the_first_logged_price_for_a_bet_stays_and_repeats_add_nothing(tmp_path):
    path = tmp_path / "gaps.csv"
    first = gap_log.rows_to_log(gaps(), LEDGER, "2026-11-05", BEFORE)
    later = gap_log.rows_to_log(gaps({"Odds": 300.0}), LEDGER, "2026-11-05", BEFORE)
    assert gap_log.append(first, path) == 1
    assert gap_log.append(later, path) == 0                     # same bet, better price: ignored
    assert gap_log.load(path)["odds"].tolist() == [220.0]
    other = gap_log.rows_to_log(gaps({"Side": "20+", "Bet": "20+", "line": 19.5}), LEDGER,
                                "2026-11-05", BEFORE)
    assert gap_log.append(other, path) == 1                     # a different number is a new bet


@pytest.mark.parametrize("side, line, actual, expected", [
    ("Over", 24.5, 25, True), ("Over", 24.5, 24, False),
    ("Under", 6.5, 6, True), ("Under", 6.5, 7, False),
    ("25+", 24.5, 25, True), ("25+", 24.5, 24, False),
])
def test_each_kind_of_bet_wins_on_the_right_side_of_its_number(side, line, actual, expected):
    assert gap_log.won(side, line, actual) is expected


def logged(tmp_path, *overrides):
    path = tmp_path / "gaps.csv"
    for o in overrides or ({},):
        gap_log.append(gap_log.rows_to_log(gaps(o), LEDGER, "2026-11-05", BEFORE), path)
    return gap_log.load(path)


def box(pid, pts, day="2026-11-05"):
    return {"player_id": pid, "game_date": pd.Timestamp(day), "pts": pts}


def test_grading_pays_the_odds_on_a_win_and_minus_one_on_a_loss(tmp_path):
    log = logged(tmp_path, {}, {"player_id": 8, "Player": "Booker", "Side": "30+", "Bet": "30+",
                                "line": 29.5})
    games = pd.DataFrame([box(7, 11.0), box(8, 30.0)])
    out = gap_log.settle(log, games, dt.date(2026, 11, 6)).set_index("player_id")
    assert out.loc[7, "result"] == "loss" and out.loc[7, "pnl_units"] == -1.0
    assert out.loc[8, "result"] == "win" and out.loc[8, "pnl_units"] == pytest.approx(2.2)  # +220
    assert set(out["status"]) == {"settled"}


def test_a_player_who_never_played_is_void_once_the_day_is_over_and_waits_until_then(tmp_path):
    log = logged(tmp_path)
    nobody = pd.DataFrame([box(99, 10.0)])
    assert gap_log.settle(log, nobody, dt.date(2026, 11, 5)).loc[0, "status"] == "pending"
    done = gap_log.settle(log, nobody, dt.date(2026, 11, 6)).loc[0]
    assert done["status"] == "void" and done["pnl_units"] == 0.0


def test_the_summary_counts_and_splits_exact_from_estimated(tmp_path):
    log = logged(tmp_path, {}, {"player_id": 8, "Side": "Under", "Bet": "Under 6.5",
                                "line": 6.5, "Odds": -120.0, "How": "estimated"},
                 {"player_id": 9, "Side": "Over", "Bet": "Over 9.5", "line": 9.5})
    games = pd.DataFrame([box(7, 11.0), box(8, 2.0)])           # player 9 still pending
    s = gap_log.summary(gap_log.settle(log, games, dt.date(2026, 11, 5)))
    assert s["all"]["logged"] == 3 and s["all"]["graded"] == 2 and s["all"]["record"] == "1-1"
    # -120 pays 100/120 = 0.8333 on a win; the loss is -1: total -0.1667
    assert s["all"]["units"] == pytest.approx(100 / 120 - 1)
    assert s["estimated"]["record"] == "1-0" and s["exact"]["record"] == "0-1"
    assert s["all"]["roi_pct"] == pytest.approx((100 / 120 - 1) / 2 * 100)


def test_an_empty_log_summarises_to_zeros():
    s = gap_log.summary(gap_log.load(__import__("pathlib").Path("does/not/exist.csv")))
    assert s["all"] == {"logged": 0, "graded": 0, "record": "0-0", "units": 0.0, "roi_pct": 0.0}
