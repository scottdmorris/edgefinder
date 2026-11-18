"""DraftKings as a price source on the Parlay screen: its lines are priced by every model at
the early snapshot (the same request already returns them), recorded with book="draftkings",
graded against the fair close, and compared with FanDuel's price on each quote."""

import datetime as dt
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from edgefinder.api import service, suggestion_service
from edgefinder.betting.odds_math import american_to_decimal, devig_two_way, implied_prob
from edgefinder.tracking import nba_paper, nba_recording, quote_evidence

EVENT = {"event_id": "e1", "commence_time": "2099-01-01T00:00:00Z",
         "home": "Boston Celtics", "away": "Miami Heat"}
LINE = {"player": "A", "line": 20.5, "over_odds": -110, "under_odds": -110}


class Model:
    version, dispersion = "v1", 7.8

    def project(self, event, names):
        return {"A": {"player_id": 1, "mean": 25.0}}


def test_the_recorder_writes_the_book_it_is_given(tmp_path):
    path = tmp_path / "ledger.csv"
    nba_recording.record_event(EVENT, [LINE], [Model()], "2026-11-15T17:00:00+00:00",
                               "2098-12-31", path=path, book="draftkings")
    assert list(nba_paper.load_ledger(path)["book"]) == ["draftkings"]


def test_without_a_book_the_recorder_still_writes_fanduel(tmp_path):
    path = tmp_path / "ledger.csv"
    nba_recording.record_event(EVENT, [LINE], [Model()], "2026-11-15T17:00:00+00:00",
                               "2098-12-31", path=path)
    assert list(nba_paper.load_ledger(path)["book"]) == ["fanduel"]


@pytest.fixture
def script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "nba_props_snapshot.py"
    spec = importlib.util.spec_from_file_location("snapshot_under_test_dk", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_early_snapshot_prices_draftkings_lines_too(script, monkeypatch):
    calls = []
    monkeypatch.setattr(script.nba_recording, "record_event",
                        lambda event, lines, models, **kw: calls.append((kw.get("book"), lines)) or {"v1": 1})
    models = type("M", (), {"get": lambda self: [Model()]})()
    script.record_other_books(EVENT, {"fanduel": [LINE], "draftkings": [LINE]}, models)
    assert calls == [("draftkings", [LINE])]


def test_a_book_with_no_lines_or_a_failure_never_stops_the_run(script, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("anything")

    monkeypatch.setattr(script.nba_recording, "record_event", boom)
    models = type("M", (), {"get": lambda self: [Model()]})()
    script.record_other_books(EVENT, {"fanduel": [LINE], "draftkings": []}, models)
    script.record_other_books(EVENT, {"fanduel": [LINE], "draftkings": [LINE]}, models)   # must not raise


def test_a_draftkings_pick_is_graded_against_the_sportsbooks_fair_close():
    row = {c: None for c in nba_paper.COLUMNS} | {
        "game_date": "2026-11-04", "event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
        "player": "A", "player_id": 1, "line": 20.5, "over_odds": -110, "under_odds": -110,
        "model_version": "v1", "status": "pending", "stat": "points", "book": "draftkings",
        "pick_side": "over", "pick_odds": -105}
    games = pd.DataFrame({"player_id": [1], "game_date": pd.to_datetime(["2026-11-04"]), "pts": [30.0],
                          "team": ["BOS"], "opponent": ["MIA"], "game_id": ["g"], "minutes": [48.0]})
    late = pd.DataFrame([{"fetched_at": "2026-11-04T23:45:00+00:00", "phase": "late", "event_id": "e1",
                          "player": "A", "line": 20.5, "over_odds": -125, "under_odds": 105}])
    out = nba_paper.settle(pd.DataFrame([row], columns=nba_paper.COLUMNS), games, late,
                           dt.date(2026, 11, 6), book_snapshots=late.assign(book="draftkings"))
    fair = devig_two_way(implied_prob(-125), implied_prob(105))[0]
    assert out.loc[0, "clv_novig_pct"] == pytest.approx((american_to_decimal(-105) * fair - 1) * 100)


def test_draftkings_has_a_display_name():
    assert service.BOOK_NAMES["draftkings"] == "DraftKings"


def test_each_book_is_compared_with_the_other_sportsbook():
    fanduel, draftkings = pd.DataFrame({"x": [1]}), pd.DataFrame({"book": ["draftkings", "other"]})
    own, other, name = suggestion_service.price_sources("draftkings", fanduel, draftkings)
    assert list(own["book"]) == ["draftkings"] and other is fanduel and name == "FanDuel"
    own, other, name = suggestion_service.price_sources("fanduel", fanduel, draftkings)
    assert own is fanduel and list(other["book"]) == ["draftkings"] and name == "DraftKings"
    own, other, _ = suggestion_service.price_sources("kalshi", fanduel, draftkings)
    assert own.empty and other.empty


def test_a_comparison_names_the_book_it_came_from():
    row = pd.Series({"stat_key": "points", "event_id": "e1", "Player": "A", "Side": "Over",
                     "line": 20.5, "Odds": -110})
    snaps = pd.DataFrame([{"event_id": "e1", "player": "A", "fetched_at": "2026-11-04T20:00:00Z",
                           "line": 20.5, "over_odds": -105, "under_odds": -115}])
    found = quote_evidence.comparisons(row, snaps, pd.Timestamp("2026-11-04T20:30:00Z"),
                                       "2026-11-05T00:00:00Z", book="FanDuel")
    assert found[0]["book"] == "FanDuel"

def test_the_record_lists_draftkings_picks_on_their_own():
    from edgefinder.api import record
    settled = {"book": "draftkings", "stat": "points", "status": "settled", "pick_side": "over",
               "pick_odds": -110, "result": "win", "pnl_units": .91, "clv_novig_pct": 2.0}
    ledger = pd.DataFrame([settled], columns=nba_paper.COLUMNS)
    assert [b["name"] for b in record.by_book(ledger)] == ["DraftKings"]
    assert [c["name"] for c in record._clv(ledger)] == ["DraftKings"]
