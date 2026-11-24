"""Game moneylines from PropLine's bulk request: parsed, archived per due game, and turned
into each side's no-vig win chance. Nothing here touches the real API."""

import pandas as pd
import pytest

from edgefinder.data import nba_moneylines, propline

EVENT = {"event_id": "oa1", "commence_time": "2026-11-24T00:00:00Z",
         "home": "Charlotte Hornets", "away": "Memphis Grizzlies"}


def h2h(away, home, line_type="main", period=None, changed="2026-11-23T03:00:00Z"):
    return {"key": "h2h", "line_type": line_type, "period": period, "outcomes": [
        {"name": "Charlotte", "side": "home", "price": home, "last_change_at": changed},
        {"name": "Memphis", "side": "away", "price": away, "last_change_at": changed}]}


GAME = {"id": 731168, "commence_time": "2026-11-24T00:00:00Z", "live": False,
        "home_team": "Charlotte Hornets", "away_team": "Memphis Grizzlies",
        "bookmakers": [
            {"key": "fanduel", "markets": [h2h(-150, 128), h2h(-120, 100, period="1h"),
                                           {"key": "player_points", "line_type": "main", "outcomes": []}]},
            {"key": "draftkings", "markets": [h2h(-145, 122, changed="2026-11-23T04:00:00Z")]},
            {"key": "bovada", "markets": [h2h(-140, 120)]}]}


def test_each_books_full_game_moneyline_is_read_by_side():
    rows = {r["book"]: r for r in nba_moneylines.parse(GAME)}
    assert set(rows) == {"fanduel", "draftkings"}                 # no bovada, no first half
    assert (rows["fanduel"]["away_odds"], rows["fanduel"]["home_odds"]) == (-150, 128)
    assert rows["draftkings"]["changed_at"] == "2026-11-23T04:00:00Z"


def test_a_moneyline_missing_a_side_is_skipped():
    one_sided = GAME | {"bookmakers": [{"key": "fanduel", "markets": [
        {"key": "h2h", "line_type": "main", "outcomes": [{"side": "home", "price": 120}]}]}]}
    assert nba_moneylines.parse(one_sided) == []
    assert nba_moneylines.parse({"bookmakers": None}) == []


def test_win_chances_have_the_vig_removed_and_sum_to_100():
    away, home = nba_moneylines.win_pcts(-150, 128)
    assert away == pytest.approx(57.8, abs=0.05) and home == pytest.approx(42.2, abs=0.05)
    assert away + home == pytest.approx(100.0)
    assert nba_moneylines.win_pcts(-110, -110) == (50.0, 50.0)


def test_only_due_games_that_have_not_tipped_are_archived(tmp_path):
    path = tmp_path / "ml.csv"
    other = EVENT | {"event_id": "oa2", "home": "Boston Celtics"}
    assert nba_moneylines.archive([GAME], [(EVENT, "early"), (other, "early")], "t1", path) == 2
    assert nba_moneylines.archive([GAME | {"live": True}], [(EVENT, "late")], "t2", path) == 0
    saved = pd.read_csv(path)
    assert list(saved.columns) == nba_moneylines.COLUMNS and len(saved) == 2
    assert set(saved["event_id"]) == {"oa1"} and set(saved["phase"]) == {"early"}
    assert nba_moneylines.archive([], [(EVENT, "early")], "t3", tmp_path / "none.csv") == 0
    assert not (tmp_path / "none.csv").exists()


def test_the_latest_price_of_the_chosen_book_wins_and_other_books_fill_in(tmp_path):
    path = tmp_path / "ml.csv"
    nba_moneylines.archive([GAME], [(EVENT, "early")], "2026-11-23T15:00:00+00:00", path)
    later = GAME | {"bookmakers": [{"key": "fanduel", "markets": [h2h(-170, 142)]}]}
    nba_moneylines.archive([later], [(EVENT, "late")], "2026-11-23T23:00:00+00:00", path)
    frame = nba_moneylines.load(path)
    fanduel = nba_moneylines.latest(frame, "fanduel")["oa1"]
    assert (fanduel["book"], fanduel["away_odds"], fanduel["home_odds"]) == ("fanduel", -170, 142)
    assert fanduel["away_pct"] + fanduel["home_pct"] == pytest.approx(100.0)
    assert fanduel["as_of"] == "2026-11-23T23:00:00+00:00"
    assert nba_moneylines.latest(frame, "draftkings")["oa1"]["away_odds"] == -145
    assert nba_moneylines.latest(frame, "kalshi")["oa1"]["book"] == "fanduel"   # no Kalshi moneyline
    assert nba_moneylines.latest(nba_moneylines.load(tmp_path / "missing.csv"), "fanduel") == {}


def test_the_bulk_request_asks_for_moneylines_without_a_second_call(monkeypatch):
    monkeypatch.setenv("PROPLINE_API_KEY", "secret-key")
    calls = []

    class Response:
        ok, status_code, headers = True, 200, {}

        def json(self):
            return [GAME]
    propline.fetch_slate(get=lambda url, **kw: calls.append(kw) or Response())
    assert len(calls) == 1 and "h2h" in calls[0]["params"]["markets"].split(",")


def _script():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "nba_props_snapshot.py"
    spec = importlib.util.spec_from_file_location("snapshot_under_test_moneylines", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


def test_the_snapshot_job_archives_moneylines_and_survives_their_failure(monkeypatch):
    script = _script()
    task = type("Task", (), {"event": EVENT, "phase": "late"})()
    monkeypatch.setenv("PROPLINE_API_KEY", "k")
    monkeypatch.setattr(propline, "fetch_slate", lambda: ([GAME], 900))
    script.archive_propline([task], None)
    assert len(pd.read_csv(nba_moneylines.MONEYLINES_PATH)) == 2
    props = []
    monkeypatch.setattr(propline, "archive", lambda *args: props.append(args) or 0)

    def broken(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(nba_moneylines, "archive", broken)
    script.archive_propline([task], None)                       # logged, not raised
    assert len(props) == 1                                      # the props archive still ran
    assert len(pd.read_csv(nba_moneylines.MONEYLINES_PATH)) == 2
