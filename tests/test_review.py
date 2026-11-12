"""The Last night review and the recommended model, against a small made-up ledger."""

import datetime as dt

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from edgefinder.api import app as api_app
from edgefinder.api import service
from edgefinder.tracking import nba_paper

DAY = "2026-11-04"
WHEN = "2026-11-04T17:00:00+00:00"
EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Boston Celtics", "away": "Milwaukee Bucks"}
# player, id, line, what he scored, minutes
NIGHT = [("Jaylen Brown", 1, 24.5, 31, 36.0), ("Sam Hauser", 2, 9.5, 2, 8.0)]


def _ledger(models=("minutes-v1", "context-v2"), settled=True) -> pd.DataFrame:
    rows = []
    for version in models:
        for name, pid, line, _, _ in NIGHT:
            quote = {"player": name, "line": line, "over_odds": -110, "under_odds": -110}
            rows += nba_paper.build_ledger_rows(
                EVENT, [quote], {name: {"player_id": pid, "mean": line + 6}}, WHEN, DAY,
                model_version=version, dispersion=7.8)
    ledger = pd.DataFrame(rows, columns=nba_paper.COLUMNS)
    if settled:
        actual = {pid: scored for _, pid, _, scored, _ in NIGHT}
        ledger["actual"] = ledger["player_id"].map(actual).astype(float)
        ledger["went_over"] = ledger["actual"] > ledger["line"]
        ledger["status"] = "settled"
        won = ledger["went_over"] == (ledger["pick_side"] == "over")
        ledger["result"] = won.map({True: "win", False: "loss"})
        ledger["pnl_units"] = won.map({True: 0.91, False: -1.0})
    return ledger


def _logs() -> pd.DataFrame:
    rows = []
    for _, pid, _, scored, minutes in NIGHT:
        for n in range(10):                                   # ten earlier games at 30 minutes
            rows.append({"player_id": pid, "game_date": pd.Timestamp("2026-10-20") + pd.Timedelta(days=n),
                         "pts": 20, "reb": 5, "ast": 4, "fg3m": 2, "minutes": 30.0, "season": "2026-27"})
        rows.append({"player_id": pid, "game_date": pd.Timestamp(DAY), "pts": scored, "reb": 7,
                     "ast": 3, "fg3m": 1, "minutes": minutes, "season": "2026-27"})
    return pd.DataFrame(rows)


@pytest.fixture
def client(monkeypatch):
    service.clear_cache()
    monkeypatch.setattr(service, "today", lambda: dt.date(2026, 11, 5))
    monkeypatch.setattr(service, "load_ledger", _ledger)
    monkeypatch.setattr(service, "load_games", _logs)
    yield TestClient(api_app.app)
    service.clear_cache()


def test_the_review_defaults_to_the_latest_graded_day_and_scores_each_model(client):
    body = client.get("/api/review").json()
    assert body["date"] == DAY and [d["date"] for d in body["days"]] == [DAY]
    assert {m["short"]: m["record"] for m in body["models"]} == {"Minutes": "1-1", "Shot profile": "1-1"}
    assert body["pending"] == 0


def test_models_that_liked_the_same_bet_share_a_row_and_misses_come_first(client):
    picks = client.get("/api/review").json()["picks"]
    assert [(p["player"], p["status"]) for p in picks] == [("Sam Hauser", "Missed"), ("Jaylen Brown", "Hit")]
    assert picks[0]["models"] == ["Minutes", "Shot profile"]
    assert picks[0]["actual"] == 2 and picks[0]["bet"] == "Over 9.5 points"


def test_a_miss_on_a_short_night_says_how_few_minutes_he_played(client):
    miss = client.get("/api/review").json()["misses"][0]
    assert miss["player"] == "Sam Hauser"
    assert miss["note"] == "Played 8 minutes, usually 30"


def test_a_day_with_nothing_graded_is_a_404(client, monkeypatch):
    monkeypatch.setattr(service, "load_ledger", lambda: _ledger(settled=False))
    service.clear_cache()
    assert client.get("/api/review").status_code == 404
    assert client.get("/api/review", params={"date": "2020-01-01"}).status_code == 404


def test_a_slip_is_graded_leg_by_leg_from_the_box_scores(client):
    legs = [{"player_id": 1, "stat": "points", "side": "Over", "line": 24.5},
            {"player_id": 1, "stat": "rebounds", "side": "Under", "line": 6.5},
            {"player_id": 2, "stat": "points", "side": "10+", "line": 9.5},
            {"player_id": 99, "stat": "points", "side": "Over", "line": 9.5}]
    body = client.post("/api/review/slip", json={"date": DAY, "legs": legs}).json()
    assert [leg["status"] for leg in body["legs"]] == ["Hit", "Missed", "Missed", "Didn't play"]
    assert body["legs"][0]["actual"] == 31
    assert body["legs"][2]["note"] == "Played 8 minutes, usually 30"
    assert (body["status"], body["hit"], body["missed"]) == ("Missed", 1, 2)


def test_a_slip_for_a_day_without_box_scores_is_not_graded_yet(client):
    legs = [{"player_id": 1, "stat": "points", "side": "Over", "line": 24.5}]
    body = client.post("/api/review/slip", json={"date": "2026-11-05", "legs": legs}).json()
    assert body["status"] == "Not graded yet" and body["legs"][0]["actual"] is None


def test_an_unknown_stat_is_rejected(client):
    legs = [{"player_id": 1, "stat": "steals", "side": "Over", "line": 1.5}]
    assert client.post("/api/review/slip", json={"date": DAY, "legs": legs}).status_code == 422


def test_the_most_accurate_model_is_recommended_once_enough_lines_are_graded(client, monkeypatch):
    standing = {"minutes-v1": {"record": "4-6", "settled": 10, "lines": 120, "brier": 0.26},
                "context-v2": {"record": "6-4", "settled": 10, "lines": 120, "brier": 0.25}}
    monkeypatch.setattr(service, "model_standing", lambda book: standing)
    board = client.get("/api/board").json()
    assert board["model"] == "context-v2"
    first = board["models"][0]
    assert (first["id"], first["recommended"], first["record"]) == ("context-v2", True, "6-4")
    assert client.get("/api/board", params={"model": "minutes-v1"}).json()["model"] == "minutes-v1"


def test_no_model_is_recommended_on_a_thin_record(client):
    board = client.get("/api/board").json()                   # two graded lines only
    assert not any(m["recommended"] for m in board["models"])
