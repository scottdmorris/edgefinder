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
    monkeypatch.setattr(script, "record_propline", lambda *args: 0)   # never the real ledger
    script.archive_propline([task], None)                 # no key: nothing happens
    monkeypatch.setenv("PROPLINE_API_KEY", "k")
    monkeypatch.setattr(propline, "fetch_slate", lambda: ([GAME], 900))
    script.archive_propline([task], None)
    assert len(pd.read_csv(propline.LINES_PATH)) == 3
    def broken():
        raise propline.PropLineError("PropLine returned HTTP 500")
    monkeypatch.setattr(propline, "fetch_slate", broken)
    script.archive_propline([task], None)                 # logged, not raised


# ---- pricing FanDuel's other stats ----------------------------------------------------------

from edgefinder.models import nba_stat_model  # noqa: E402
from edgefinder.tracking import nba_kalshi_ledger, nba_paper  # noqa: E402

FUTURE = {"event_id": "oa1", "commence_time": "2099-11-24T00:00:00Z",
          "home": "Charlotte Hornets", "away": "Memphis Grizzlies"}
FUTURE_GAME = GAME | {"commence_time": "2099-11-24T00:00:00Z"}


def load_snapshot_script():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "nba_props_snapshot.py"
    spec = importlib.util.spec_from_file_location("snapshot_under_test_propline_picks", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


class FakeModels:
    def __init__(self):
        self.asked = []

    def kalshi_models(self):
        def project(event, stat, names):
            self.asked.append((stat, names))
            return {name: {"player_id": 7, "mean": 14.0} for name in names}
        return [nba_kalshi_ledger.KalshiModel(
            "ewma-v1", {s: stat.dispersion for s, stat in nba_stat_model.STATS.items()}, project)]


def test_only_fanduels_non_points_lines_with_both_sides_are_priced():
    assert propline.new_fanduel_lines(GAME) == {
        "rebounds": [{"player": "Edey", "line": 11.5, "over_odds": -105, "under_odds": -125}]}


def test_fanduel_rebounds_are_priced_into_the_ledger_under_their_own_stat(tmp_path):
    script, models, path = load_snapshot_script(), FakeModels(), tmp_path / "ledger.csv"
    assert script.record_propline([FUTURE_GAME], [FUTURE], models, path=path) == 1
    assert models.asked == [("rebounds", ["Edey"])]
    row = nba_paper.load_ledger(path).iloc[0]
    assert (row["book"], row["stat"], row["model_version"], row["line"]) == (
        "fanduel", "rebounds", "ewma-v1", 11.5)
    assert row["pick_side"] == "over"                     # 14 projected against 11.5
    assert script.record_propline([FUTURE_GAME], [FUTURE], models, path=path) == 0   # no repeats
    assert script.record_propline([FUTURE_GAME | {"live": True}], [FUTURE], models, path=path) == 0
    untouched = FakeModels()
    assert script.record_propline([FUTURE_GAME], [FUTURE | {"home": "Boston Celtics"}], untouched,
                                  path=path) == 0
    assert untouched.asked == []


def test_only_early_games_are_priced_and_a_pricing_failure_never_stops_the_run(monkeypatch):
    script = load_snapshot_script()
    monkeypatch.setenv("PROPLINE_API_KEY", "k")
    monkeypatch.setattr(propline, "fetch_slate", lambda: ([FUTURE_GAME], 900))
    priced = []
    monkeypatch.setattr(script, "record_propline", lambda games, events, models: priced.append(events) or 1)
    task = lambda phase: type("Task", (), {"event": FUTURE, "phase": phase})()  # noqa: E731
    script.archive_propline([task("late")], FakeModels())
    assert priced == []
    script.archive_propline([task("early"), task("late")], FakeModels())
    assert priced == [[FUTURE]]

    def broken(*args):
        raise RuntimeError("model failed")
    monkeypatch.setattr(script, "record_propline", broken)
    script.archive_propline([task("early")], FakeModels())       # logged, not raised


# ---- grading and closing them ---------------------------------------------------------------

def ledger_row(stat, book="fanduel", line=11.5, odds=-105):
    return {c: None for c in nba_paper.COLUMNS} | {
        "recorded_at": "2026-11-23T20:00:00Z", "game_date": "2026-11-23", "event_id": "oa1",
        "commence_time": "2026-11-24T00:00:00Z", "player": "Edey", "player_id": 7, "line": line,
        "over_odds": odds, "under_odds": -125, "model_version": "ewma-v1",
        "model_p_over": .6, "fair_p_over": .5, "status": "pending", "stat": stat, "book": book,
        "pick_side": "over", "pick_odds": odds}


def late_line(book, stat="rebounds", line=11.5, over=-130, under=100, fetched="2026-11-23T23:30:00Z"):
    return {"fetched_at": fetched, "phase": "late", "event_id": "oa1", "propline_event_id": 1,
            "commence_time": "2026-11-24T00:00:00Z", "home": "h", "away": "a", "book": book,
            "stat": stat, "player": "Edey", "player_id": "nba:7", "line": line,
            "over_odds": over, "under_odds": under, "changed_at": None}


def test_fanduel_rebounds_are_graded_and_closed_from_proplines_late_line():
    rebounds = nba_stat_model.STATS["rebounds"].column
    games = pd.DataFrame({"player_id": [7], "game_date": pd.to_datetime(["2026-11-23"]),
                          "pts": [20.0], rebounds: [13.0]})
    snapshots = pd.DataFrame(columns=["fetched_at", "phase", "event_id", "player", "line",
                                      "over_odds", "under_odds"])
    ledger = pd.DataFrame([ledger_row("rebounds"), ledger_row("points", line=19.5)],
                          columns=nba_paper.COLUMNS)
    pl = pd.DataFrame([late_line("fanduel"), late_line("draftkings", over=-120, under=-110),
                       late_line("fanduel", stat="points", line=19.5),
                       late_line("fanduel", over=+200, fetched="2026-11-24T01:00:00Z")],  # after tip
                      columns=propline.COLUMNS)
    out = nba_paper.settle(ledger, games, snapshots, pd.Timestamp("2026-11-25").date(),
                           propline_snapshots=pl)
    reb, pts = out.iloc[0], out.iloc[1]
    assert (reb["status"], reb["result"]) == ("settled", "win")
    assert reb["closing_over_odds"] == -130 and reb["clv_pct"] > 0
    assert reb["clv_novig_pct"] is not None and not pd.isna(reb["clv_novig_pct"])
    assert pd.isna(pts["closing_over_odds"]) and pd.isna(pts["clv_novig_pct"])  # points stay with The Odds API
