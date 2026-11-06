"""Saving Kalshi's late prices, and using them to close Kalshi picks."""

import pandas as pd
import pytest

from edgefinder.tracking import nba_kalshi_ledger as ledger_mod
from edgefinder.tracking import nba_paper
from test_nba_kalshi_ledger import EVENTS, market, one_per_game, rows_of

LATE = "2026-11-04T23:00:00+00:00"


def test_one_row_is_saved_for_each_liquid_price_in_a_game_about_to_tip(tmp_path):
    path = tmp_path / "kalshi_snapshots.csv"
    assert ledger_mod.archive_closing(one_per_game(), EVENTS, LATE, path) == 7
    saved = ledger_mod.load_snapshots(path)
    assert list(saved.columns) == ledger_mod.SNAPSHOT_COLUMNS and len(saved) == 7
    first = saved[saved["event_id"] == "e1"].iloc[0]
    # yes ask 0.58 -> over at -138 ; no ask 0.46 -> under at +117 ; "25+" is the line 24.5
    assert (first["stat"], first["line"], first["over_odds"], first["under_odds"]) == (
        "points", 24.5, -138, 117)
    assert first["fetched_at"] == LATE


def test_thin_markets_unmatched_games_and_empty_input_save_nothing_and_make_no_file(tmp_path):
    path = tmp_path / "none.csv"
    thin = rows_of(market("KXNBAPTS", "PHI", "DET", "PLAYER", "Thin Tim", 25,
                          yes_bid="0.0500", yes_ask="0.3300", volume="3.0"))
    elsewhere = rows_of(market("KXNBAPTS", "GSW", "MIA", "PLAYER", "Nowhere Ned", 25))
    assert ledger_mod.archive_closing(thin, EVENTS, LATE, path) == 0
    assert ledger_mod.archive_closing(elsewhere, EVENTS, LATE, path) == 0
    assert ledger_mod.archive_closing([], EVENTS, LATE, path) == 0
    assert not path.exists()


def test_each_call_appends_so_the_latest_price_can_be_chosen_later(tmp_path):
    path = tmp_path / "kalshi_snapshots.csv"
    ledger_mod.archive_closing(one_per_game(), EVENTS, "2026-11-04T22:00:00+00:00", path)
    ledger_mod.archive_closing(one_per_game(), EVENTS, "2026-11-04T23:00:00+00:00", path)
    assert len(ledger_mod.load_snapshots(path)) == 14


def test_no_saved_prices_reads_as_an_empty_table_with_the_columns(tmp_path):
    table = ledger_mod.load_snapshots(tmp_path / "missing.csv")
    assert table.empty and list(table.columns) == ledger_mod.SNAPSHOT_COLUMNS


# ---- closing a Kalshi pick ------------------------------------------------------------------------------

def pick(side="over", pick_odds=100, line=24.5, book="kalshi", event="e1", player="Cade"):
    base = {c: None for c in nba_paper.COLUMNS} | {
        "game_date": "2026-11-04", "event_id": event, "commence_time": "2026-11-05T00:00:00Z",
        "player": player, "player_id": 1, "line": line, "over_odds": 100, "under_odds": -120,
        "model_version": "ewma-v1", "status": "pending", "stat": "points", "book": book,
        "pick_side": side, "pick_odds": pick_odds}
    return base


def closing(**kwargs):
    row = {"fetched_at": LATE, "event_id": "e1", "stat": "points", "player": "Cade",
           "line": 24.5, "over_odds": -150, "under_odds": 130} | kwargs
    return pd.DataFrame([row], columns=ledger_mod.SNAPSHOT_COLUMNS)


def settle(rows, snapshots):
    games = pd.DataFrame({"player_id": [1], "game_date": pd.to_datetime(["2026-11-04"]),
                          "pts": [30.0]})
    empty = pd.DataFrame(columns=["fetched_at", "phase", "event_id", "player", "line",
                                  "over_odds", "under_odds"])
    ledger = pd.DataFrame(rows, columns=nba_paper.COLUMNS)
    return nba_paper.settle(ledger, games, empty, pd.Timestamp("2026-11-06").date(), snapshots)


def test_an_over_that_the_market_later_agreed_with_has_positive_closing_value():
    # took +100 (implied 50%); it closed at -150 (60%): (0.60 - 0.50) / 0.50 = +20%
    out = settle([pick("over", 100)], closing(over_odds=-150))
    assert out.loc[0, "clv_pct"] == pytest.approx(20.0)
    assert out.loc[0, "closing_over_odds"] == -150 and out.loc[0, "closing_line"] == 24.5


def test_an_under_is_judged_on_the_unders_closing_price():
    # took +100 (50%); the under closed at -200 (66.67%): (0.6667 - 0.5) / 0.5 = +33.33%
    out = settle([pick("under", 100)], closing(under_odds=-200))
    assert out.loc[0, "clv_pct"] == pytest.approx(100 / 3)


def test_a_price_that_drifted_against_us_is_negative():
    # took -150 (60%); it closed at +100 (50%): (0.50 - 0.60) / 0.60 = -16.67%
    out = settle([pick("over", -150)], closing(over_odds=100))
    assert out.loc[0, "clv_pct"] == pytest.approx(-100 / 6)


def test_kalshi_has_no_line_movement_and_a_different_line_does_not_close_the_pick():
    assert pd.isna(settle([pick()], closing()).loc[0, "line_move"])
    other_line = settle([pick(line=24.5)], closing(line=29.5))
    assert pd.isna(other_line.loc[0, "clv_pct"]) and pd.isna(other_line.loc[0, "closing_over_odds"])


def test_the_latest_saved_price_is_the_closing_price():
    both = pd.concat([closing(fetched_at="2026-11-04T22:00:00+00:00", over_odds=200),
                      closing(fetched_at="2026-11-04T23:30:00+00:00", over_odds=-150)])
    assert settle([pick()], both).loc[0, "clv_pct"] == pytest.approx(20.0)


def test_kalshi_prices_never_close_fanduel_rows_and_no_snapshots_changes_nothing():
    fanduel = settle([pick(book="fanduel")], closing())
    assert pd.isna(fanduel.loc[0, "clv_pct"])
    assert pd.isna(settle([pick()], None).loc[0, "clv_pct"])
    assert pd.isna(settle([pick()], closing().iloc[0:0]).loc[0, "clv_pct"])
