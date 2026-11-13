"""A second sportsbook's prices fetched in the same request as FanDuel's, kept in their own
file, and compared with FanDuel's. Nothing here touches the real API or data folder."""

import pandas as pd
import pytest

from edgefinder.data import nba_props
from edgefinder.tracking import book_gaps
from test_nba_props_extra import EVENT, FakeResponse, api  # noqa: F401  (api is a fixture)


def outcomes(player, line, over, under):
    return [{"name": "Over", "description": player, "price": over, "point": line},
            {"name": "Under", "description": player, "price": under, "point": line}]


def payload(**books):
    return {"bookmakers": [{"key": key, "markets": [{"key": "player_points", "outcomes": rows}]}
                           for key, rows in books.items()]}


BOTH = payload(fanduel=outcomes("A", 20.5, -110, -110), draftkings=outcomes("A", 21.5, -120, -105))


# ---- fetching --------------------------------------------------------------------------------------

def test_each_book_is_read_from_its_own_part_of_the_response():
    assert nba_props.parse_player_lines(BOTH)[0]["line"] == 20.5
    assert nba_props.parse_player_lines(BOTH, book="draftkings") == [
        {"player": "A", "line": 21.5, "over_odds": -120, "under_odds": -105}]


def test_both_books_come_from_one_request_in_one_region(api):  # noqa: F811
    api["response"] = FakeResponse(BOTH)
    books = nba_props.fetch_event_books(EVENT)
    assert len(api["calls"]) == 1                       # a second request would cost quota
    params = api["calls"][0]["params"]
    assert params["bookmakers"] == "fanduel,draftkings" and params["regions"] == "us"
    assert books["fanduel"][0]["line"] == 20.5 and books["draftkings"][0]["line"] == 21.5


def test_a_book_that_lists_nothing_is_an_empty_list_not_an_error(api):  # noqa: F811
    api["response"] = FakeResponse(payload(fanduel=outcomes("A", 20.5, -110, -110)))
    assert nba_props.fetch_event_books(EVENT)["draftkings"] == []


def test_the_fanduel_only_fetch_still_asks_for_fanduel_alone(api):  # noqa: F811
    api["response"] = FakeResponse(BOTH)
    assert nba_props.fetch_event_lines(EVENT)[0]["line"] == 20.5
    assert api["calls"][0]["params"]["bookmakers"] == "fanduel"


# ---- the archive -----------------------------------------------------------------------------------

def test_other_books_are_archived_with_the_book_named(tmp_path):
    path = tmp_path / "books.csv"
    lines = nba_props.parse_player_lines(BOTH, book="draftkings")
    nba_props.append_book_snapshot(EVENT, "early", "draftkings", lines, "2026-11-04T20:00:00+00:00", path)
    nba_props.append_book_snapshot(EVENT, "late", "draftkings", lines, "2026-11-04T23:00:00+00:00", path)
    saved = nba_props.load_book_snapshots(path)
    assert list(saved.columns) == nba_props.BOOK_COLUMNS
    assert list(saved["book"]) == ["draftkings", "draftkings"]
    assert list(saved["phase"]) == ["early", "late"] and saved.loc[0, "line"] == 21.5


def test_no_archive_yet_reads_as_an_empty_table(tmp_path):
    saved = nba_props.load_book_snapshots(tmp_path / "missing.csv")
    assert saved.empty and list(saved.columns) == nba_props.BOOK_COLUMNS


def test_the_fanduel_archive_keeps_its_own_columns(tmp_path):
    path = tmp_path / "fanduel.csv"
    nba_props.append_snapshot(EVENT, "early", nba_props.parse_player_lines(BOTH),
                              "2026-11-04T20:00:00+00:00", path)
    assert "book" not in nba_props.load_snapshots(path).columns


# ---- comparing the two books -----------------------------------------------------------------------

def line(player, number, over, under):
    return {"player": player, "line": number, "over_odds": over, "under_odds": under}


def only(table, player):
    return table[table["player"] == player].iloc[0]


def test_on_the_same_number_the_edge_is_fanduels_payout_at_the_other_books_fair_chance():
    # DraftKings -150/+120 is 60% / 45.45% with the margin in; fair over = 0.6 / 1.0545 = 56.9%
    table = book_gaps.compare([line("A", 20.5, 100, -120)], [line("A", 20.5, -150, 120)])
    row = only(table, "A")
    fair_over = 0.6 / (0.6 + 100 / 220)
    assert row["other_fair_over"] == pytest.approx(fair_over)
    assert row["over_edge"] == pytest.approx(fair_over * 2.0 - 1.0)             # FanDuel pays 2.0
    assert row["under_edge"] == pytest.approx((1 - fair_over) * (1 + 100 / 120) - 1.0)
    assert row["line_diff"] == 0.0


def test_two_books_with_the_same_prices_show_only_the_margin_as_a_negative_edge():
    row = only(book_gaps.compare([line("A", 20.5, -110, -110)], [line("A", 20.5, -110, -110)]), "A")
    assert row["over_edge"] == pytest.approx(0.5 * (1 + 100 / 110) - 1.0)
    assert row["over_edge"] < 0 and row["under_edge"] < 0


def test_different_numbers_are_reported_as_a_line_difference_with_no_edge():
    row = only(book_gaps.compare([line("A", 20.5, -110, -110)], [line("A", 22.5, -110, -110)]), "A")
    assert row["line_diff"] == pytest.approx(-2.0)          # FanDuel's number is 2 lower
    assert pd.isna(row["over_edge"]) and pd.isna(row["under_edge"])


def test_a_player_only_one_book_lists_is_left_out():
    table = book_gaps.compare([line("A", 20.5, -110, -110), line("B", 9.5, -110, -110)],
                              [line("A", 20.5, -110, -110)])
    assert list(table["player"]) == ["A"]


def test_a_one_sided_price_cannot_be_made_fair_so_it_has_no_edge():
    row = only(book_gaps.compare([line("A", 20.5, -110, -110)], [line("A", 20.5, -130, None)]), "A")
    assert pd.isna(row["other_fair_over"]) and pd.isna(row["over_edge"])


def test_nothing_to_compare_is_an_empty_table_with_the_columns():
    table = book_gaps.compare([], [])
    assert table.empty and list(table.columns) == book_gaps.COLUMNS


def test_worth_a_look_counts_big_edges_and_different_numbers_only():
    table = book_gaps.compare(
        [line("A", 20.5, 100, -120),       # +13.8% on the over
         line("B", 9.5, -110, -110),       # same prices: nothing
         line("C", 14.5, -110, -110)],     # a different number
        [line("A", 20.5, -150, 120), line("B", 9.5, -110, -110), line("C", 15.5, -110, -110)])
    assert list(book_gaps.worth_a_look(table)["player"]) == ["A", "C"]
