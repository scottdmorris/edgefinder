"""PropLine as a second source of FanDuel and DraftKings lines for all four stats: one request
a run, main lines only, archived in their own file. Nothing here touches the real API."""

import pandas as pd
import pytest
import requests

from edgefinder.data import propline

EVENT = {"event_id": "oa1", "commence_time": "2026-11-24T00:00:00Z",
         "home": "Charlotte Hornets", "away": "Memphis Grizzlies"}


def outcome(name, player, price, point, changed="2026-11-23T03:00:00Z"):
    return {"name": name, "description": player, "price": price, "point": point,
            "player_id": f"nba:{player}", "last_change_at": changed}


def market(key, outcomes, line_type="main"):
    return {"key": key, "line_type": line_type, "outcomes": outcomes}


GAME = {"id": 731168, "commence_time": "2026-11-24T00:00:00Z", "live": False,
        "home_team": "Charlotte Hornets", "away_team": "Memphis Grizzlies",
        "bookmakers": [
            {"key": "fanduel", "markets": [
                market("player_points", [outcome("Over", "Miller", -112, 21.5),
                                         outcome("Under", "Miller", -118, 21.5, "2026-11-23T03:30:00Z")]),
                market("player_rebounds", [outcome("Over", "Edey", -105, 11.5),
                                           outcome("Under", "Edey", -125, 11.5)]),
                market("player_rebounds", [outcome("6+ Rebounds", "Miller", -150, None)], "milestone"),
                market("player_blocks", [outcome("Over", "Edey", 100, 1.5)])]},
            {"key": "draftkings", "markets": [
                market("player_threes", [outcome("Over", "Miller", 120, 3.5)])]},
            {"key": "bovada", "markets": [
                market("player_points", [outcome("Over", "Miller", -110, 21.5)])]}]}


class Response:
    def __init__(self, payload, status=200, remaining="990"):
        self.payload, self.status_code = payload, status
        self.ok = status < 400
        self.headers = {"x-daily-remaining": remaining} if remaining else {}

    def json(self):
        return self.payload


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("PROPLINE_API_KEY", "secret-key")


def test_main_lines_from_both_books_are_paired_and_everything_else_is_skipped():
    rows = {(r["book"], r["stat"], r["player"]): r for r in propline.parse_lines(GAME)}
    assert set(rows) == {("fanduel", "points", "Miller"), ("fanduel", "rebounds", "Edey"),
                         ("draftkings", "threes", "Miller")}      # no milestone, blocks or bovada
    miller = rows[("fanduel", "points", "Miller")]
    assert (miller["line"], miller["over_odds"], miller["under_odds"]) == (21.5, -112, -118)
    assert miller["player_id"] == "nba:Miller" and miller["changed_at"] == "2026-11-23T03:30:00Z"
    assert rows[("draftkings", "threes", "Miller")]["under_odds"] is None


def test_one_request_carries_the_key_in_a_header_and_reports_what_is_left(key):
    calls = []
    games, left = propline.fetch_slate(get=lambda url, **kw: calls.append((url, kw)) or Response([GAME]))
    assert games == [GAME] and left == 990 and len(calls) == 1
    url, kw = calls[0]
    assert "secret-key" not in url and kw["headers"] == {"X-API-Key": "secret-key"}
    assert kw["params"]["bookmakers"] == "fanduel,draftkings"
    assert kw["params"]["markets"].split(",") == list(propline.MARKETS)
    assert propline.fetch_slate(get=lambda *a, **k: Response([], remaining=None))[1] is None


def test_failures_raise_without_the_key(key):
    def broken(*a, **k):
        raise requests.ConnectionError("https://x?apiKey=secret-key")
    for get in (broken, lambda *a, **k: Response({}, status=429), lambda *a, **k: Response({"error": 1})):
        with pytest.raises(propline.PropLineError) as info:
            propline.fetch_slate(get=get)
        assert "secret-key" not in str(info.value)


def test_no_key_means_no_request(monkeypatch, tmp_path):
    monkeypatch.delenv("PROPLINE_API_KEY", raising=False)
    monkeypatch.setattr(propline, "KEY_PATH", tmp_path / "missing.txt")
    assert propline.get_api_key() is None
    with pytest.raises(propline.PropLineError, match="No PropLine key"):
        propline.fetch_slate(get=lambda *a, **k: pytest.fail("must not call"))
    (tmp_path / "missing.txt").write_text("  file-key \n", encoding="utf-8")
    assert propline.get_api_key() == "file-key"


def test_games_match_on_teams_and_a_nearby_tip():
    assert propline.match_game(EVENT, [GAME]) is GAME
    assert propline.match_game(EVENT | {"commence_time": "2026-11-25T00:00:00Z"}, [GAME]) is None
    assert propline.match_game(EVENT | {"home": "Boston Celtics"}, [GAME]) is None


def test_only_due_games_that_have_not_tipped_are_archived(tmp_path):
    path = tmp_path / "lines.csv"
    other = EVENT | {"event_id": "oa2", "home": "Boston Celtics"}
    assert propline.archive([GAME], [(EVENT, "early"), (other, "early")], "t1", path) == 3
    assert propline.archive([GAME | {"live": True}], [(EVENT, "late")], "t2", path) == 0
    assert propline.archive([GAME], [(EVENT, "late")], "t3", path) == 3
    saved = pd.read_csv(path)
    assert list(saved.columns) == propline.COLUMNS and len(saved) == 6
    assert set(saved["phase"]) == {"early", "late"} and set(saved["event_id"]) == {"oa1"}
    assert set(saved["propline_event_id"]) == {731168}
    assert propline.archive([], [(EVENT, "early")], "t4", tmp_path / "none.csv") == 0
    assert not (tmp_path / "none.csv").exists()


def test_the_snapshot_job_saves_due_games_and_survives_a_propline_failure(monkeypatch, tmp_path):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "nba_props_snapshot.py"
    spec = importlib.util.spec_from_file_location("snapshot_under_test_propline", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    task = type("Task", (), {"event": EVENT, "phase": "early"})()
    script.archive_propline([task])                       # no key: nothing happens
    monkeypatch.setenv("PROPLINE_API_KEY", "k")
    monkeypatch.setattr(propline, "fetch_slate", lambda: ([GAME], 900))
    script.archive_propline([task])
    assert len(pd.read_csv(propline.LINES_PATH)) == 3
    def broken():
        raise propline.PropLineError("PropLine returned HTTP 500")
    monkeypatch.setattr(propline, "fetch_slate", broken)
    script.archive_propline([task])                       # logged, not raised
