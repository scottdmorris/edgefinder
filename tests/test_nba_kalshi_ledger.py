import importlib.util
import logging
from pathlib import Path

import pandas as pd
import pytest

from edgefinder.betting import negbin
from edgefinder.data import kalshi, nba_snapshot_plan
from edgefinder.models import nba_stat_model
from edgefinder.tracking import nba_kalshi_ledger as ledger_mod
from edgefinder.tracking import nba_paper, nba_parlay

RECORDED_AT = "2026-11-04T17:00:00+00:00"
VERSION = "ewma-v1"

# 7 games on the night of 2026-11-04 (Eastern). 00:00Z is 7pm EST.
GAMES = [
    ("e1", "Philadelphia 76ers", "Detroit Pistons", "PHI", "DET", "2026-11-05T00:00:00Z"),
    ("e2", "Minnesota Timberwolves", "Houston Rockets", "MIN", "HOU", "2026-11-05T00:30:00Z"),
    ("e3", "Milwaukee Bucks", "Boston Celtics", "MIL", "BOS", "2026-11-05T00:30:00Z"),
    ("e4", "Denver Nuggets", "Los Angeles Lakers", "DEN", "LAL", "2026-11-05T02:00:00Z"),
    ("e5", "Golden State Warriors", "Phoenix Suns", "GSW", "PHX", "2026-11-05T02:00:00Z"),
    ("e6", "Miami Heat", "Atlanta Hawks", "MIA", "ATL", "2026-11-05T00:00:00Z"),
    ("e7", "Dallas Mavericks", "Oklahoma City Thunder", "DAL", "OKC", "2026-11-05T01:00:00Z"),
]
EVENTS = [{"event_id": eid, "commence_time": tip, "away": away, "home": home}
          for eid, away, home, _, _, tip in GAMES]
TRICODES = {eid: (a, h) for eid, _, _, a, h, _ in GAMES}


def market(series, away, home, code, name, n, *, ymd="26NOV04", yes_bid="0.5400",
           yes_ask="0.5800", no_bid="0.4200", no_ask="0.4600", volume="473.27"):
    """A liquid market by default: 4-cent spread, 473 contracts traded."""
    return {
        "ticker": f"{series}-{ymd}{away}{home}-{home}{code}7-{n}",
        "yes_sub_title": f"{name}: {n}+",
        "title": f"{name}: {n}+ points",
        "yes_bid_dollars": yes_bid, "yes_ask_dollars": yes_ask,
        "no_bid_dollars": no_bid, "no_ask_dollars": no_ask,
        "volume_fp": volume,
    }


def rows_of(*markets):
    return kalshi.parse_markets({"markets": list(markets)})


def one_per_game():
    """One liquid points market per game; the player is named for its event."""
    return rows_of(*[
        market("KXNBAPTS", away, home, "PLAYER", f"Player {eid}", 25)
        for eid, (away, home) in TRICODES.items()])


# ---- the join ------------------------------------------------------------

def test_each_market_joins_to_its_own_game_on_a_night_of_seven():
    joined = ledger_mod.join_to_events(one_per_game(), EVENTS)
    assert sorted(joined.by_event) == [f"e{i}" for i in range(1, 8)]
    for event_id, rows in joined.by_event.items():
        assert [r["player"] for r in rows] == [f"Player {event_id}"]
        assert (rows[0]["away"], rows[0]["home"]) == TRICODES[event_id]
    assert not joined.unmatched and not joined.ambiguous and joined.illiquid == 0


def test_swapped_home_and_away_is_a_different_game_and_does_not_join():
    rows = rows_of(market("KXNBAPTS", "HOU", "MIN", "PLAYER", "Swapped Sam", 25))
    joined = ledger_mod.join_to_events(rows, EVENTS)
    assert joined.by_event == {} and len(joined.unmatched) == 1


def test_a_team_code_that_matches_no_scheduled_team_is_skipped_not_guessed():
    # Kalshi writing PHO where the NBA says PHX must not be quietly forced onto GSW @ PHX
    rows = rows_of(market("KXNBAPTS", "GSW", "PHO", "PLAYER", "Pat Hoe", 25),
                   market("KXNBAPTS", "GSW", "PHX", "PLAYER", "Pat Hex", 25))
    joined = ledger_mod.join_to_events(rows, EVENTS)
    assert [r["player"] for r in joined.by_event["e5"]] == ["Pat Hex"]
    assert [r["player"] for r in joined.unmatched] == ["Pat Hoe"]


def test_the_right_teams_on_the_wrong_date_do_not_join():
    rows = rows_of(market("KXNBAPTS", "MIN", "HOU", "PLAYER", "Next Night", 25, ymd="26NOV05"))
    assert ledger_mod.join_to_events(rows, EVENTS).by_event == {}


def test_the_date_is_the_eastern_tip_date_not_the_utc_date():
    # tip 2026-11-05T00:30Z is Nov 4 in New York: a Nov 4 ticker joins
    assert nba_snapshot_plan.tip_date(EVENTS[1]) == "2026-11-04"
    joined = ledger_mod.join_to_events(
        rows_of(market("KXNBAPTS", "MIN", "HOU", "PLAYER", "On Time", 25)), EVENTS)
    assert list(joined.by_event) == ["e2"]


def test_two_scheduled_games_with_the_same_teams_and_date_are_ambiguous_and_skipped():
    twin = dict(EVENTS[1], event_id="e2b")
    joined = ledger_mod.join_to_events(
        rows_of(market("KXNBAPTS", "MIN", "HOU", "PLAYER", "Who Knows", 25)), EVENTS + [twin])
    assert joined.by_event == {} and len(joined.ambiguous) == 1


def test_a_market_for_a_game_outside_the_schedule_is_ignored():
    rows = rows_of(market("KXNBAPTS", "MIN", "HOU", "PLAYER", "Tonight", 25))
    only_two_games = [e for e in EVENTS if e["event_id"] in ("e1", "e3")]
    assert ledger_mod.join_to_events(rows, only_two_games).by_event == {}


# ---- liquidity -----------------------------------------------------------

def test_only_liquid_markets_become_ledger_rows():
    liquid = market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 25)
    wide = market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 35,
                  yes_bid="0.0500", yes_ask="0.3300")
    quiet = market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 20, volume="3.00")
    one_sided = market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 15,
                       yes_bid="0.0000", yes_ask="0.5800")
    rows = rows_of(liquid, wide, quiet, one_sided)
    assert [r["is_liquid"] for r in rows] == [True, False, False, False]
    projections = {"e2": {"points": {"Kevin Durant": {"player_id": 1, "mean": 30.0}}}}
    out = ledger_mod.build_kalshi_ledger_rows(
        rows, EVENTS, projections, RECORDED_AT, model_version=VERSION)
    assert [r["line"] for r in out] == [24.5]
    assert ledger_mod.join_to_events(rows, EVENTS).illiquid == 3


# ---- the rows themselves -------------------------------------------------

def test_a_liquid_market_becomes_a_hand_checked_ledger_row():
    rows = rows_of(market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 25))
    projections = {"e2": {"points": {"Kevin Durant": {"player_id": 201142, "mean": 30.0}}}}
    (row,) = ledger_mod.build_kalshi_ledger_rows(
        rows, EVENTS, projections, RECORDED_AT, model_version=VERSION)
    # 25+ is "over 24.5"; yes ask $0.58 is -138 (-100*0.58/0.42 = -138.1), no ask
    # $0.46 is +117 (100*0.54/0.46 = 117.4)
    assert (row["line"], row["over_odds"], row["under_odds"]) == (24.5, -138, 117)
    # devig: 138/238 = 0.5798 and 100/217 = 0.4608; 0.5798 / (0.5798 + 0.4608) = 0.5572
    assert row["fair_p_over"] == pytest.approx(0.5572, abs=1e-3)
    assert row["model_p_over"] == pytest.approx(float(negbin.over_prob(24.5, 30.0, 7.8)))
    assert row["model_p_over"] > 0.6          # a 30-point mean clears 24.5 more often than not
    assert (row["event_id"], row["player"], row["player_id"]) == ("e2", "Kevin Durant", 201142)
    assert (row["home"], row["away"], row["game_date"]) == (
        "Houston Rockets", "Minnesota Timberwolves", "2026-11-04")
    assert (row["stat"], row["book"], row["model_version"], row["status"]) == (
        "points", "kalshi", VERSION, "pending")
    assert row["recorded_at"] == RECORDED_AT
    # blend = 0.3 * 0.6411 + 0.7 * 0.5572 = 0.5824; over EV at -138 (decimal 1.7246) is
    # 0.5824 * 1.7246 - 1 = +0.4%, under the 2% bar, so this price is logged but not a pick
    assert row["pick_side"] is None and row["pick_ev"] is None


def test_an_edge_far_from_kalshi_s_price_is_not_a_pick_however_big():
    rows = rows_of(market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 25))
    projections = {"e2": {"points": {"Kevin Durant": {"player_id": 1, "mean": 38.0}}}}
    (row,) = ledger_mod.build_kalshi_ledger_rows(
        rows, EVENTS, projections, RECORDED_AT, model_version=VERSION)
    # model 0.8165 vs Kalshi 0.5572 would be +9.5% EV, but a 26-point disagreement is far past
    # the 15-point guardrail: the model is missing something, so nothing is picked
    assert row["model_p_over"] == pytest.approx(0.8165, abs=1e-3)
    assert row["fair_p_over"] == pytest.approx(0.5572, abs=1e-3)
    assert row["pick_side"] is None and row["pick_ev"] is None


def test_the_row_key_is_event_player_line_model_stat_book():
    rows = rows_of(market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 25))
    projections = {"e2": {"points": {"Kevin Durant": {"player_id": 1, "mean": 30.0}}}}
    (row,) = ledger_mod.build_kalshi_ledger_rows(
        rows, EVENTS, projections, RECORDED_AT, model_version=VERSION)
    assert nba_paper._row_key(row) == ("e2", "Kevin Durant", 24.5, VERSION, "points", "kalshi")


@pytest.mark.parametrize("series,stat,dispersion", [
    ("KXNBAPTS", "points", 7.8), ("KXNBAREB", "rebounds", 10.7),
    ("KXNBAAST", "assists", 11.3), ("KXNBA3PT", "threes", 6.8)])
def test_each_stat_is_tagged_and_priced_with_its_own_dispersion(series, stat, dispersion):
    rows = rows_of(market(series, "MIN", "HOU", "DURANT", "Kevin Durant", 5))
    projections = {"e2": {stat: {"Kevin Durant": {"player_id": 1, "mean": 6.0}}}}
    (row,) = ledger_mod.build_kalshi_ledger_rows(
        rows, EVENTS, projections, RECORDED_AT, model_version=VERSION)
    assert row["stat"] == stat and row["book"] == "kalshi" and row["line"] == 4.5
    assert row["model_p_over"] == pytest.approx(float(negbin.over_prob(4.5, 6.0, dispersion)))


def test_a_player_without_a_projection_is_not_recorded():
    rows = rows_of(market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 25))
    assert ledger_mod.build_kalshi_ledger_rows(
        rows, EVENTS, {}, RECORDED_AT, model_version=VERSION) == []


# ---- fetching and failure isolation --------------------------------------

def test_kalshi_is_called_once_per_series():
    calls = []

    def fetch(series):
        calls.append(series)
        return {"markets": []}

    ledger_mod.fetch_kalshi_rows(fetch)
    assert sorted(calls) == sorted(kalshi.SERIES_STATS)


def test_a_failing_series_logs_one_line_and_the_others_still_come_back(caplog):
    good = market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 25)

    def fetch(series):
        if series == "KXNBAREB":
            raise kalshi.KalshiDataError("Kalshi returned HTTP 503")
        return {"markets": [good] if series == "KXNBAPTS" else []}

    with caplog.at_level(logging.INFO):
        rows = ledger_mod.fetch_kalshi_rows(fetch)
    assert [r["stat"] for r in rows] == ["points"]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "KXNBAREB" in warnings[0].getMessage()
    assert "\n" not in warnings[0].getMessage() and warnings[0].exc_info is None


def test_kalshi_being_entirely_down_yields_no_rows_and_no_exception():
    def fetch(series):
        raise kalshi.KalshiDataError("Kalshi request failed (ConnectionError)")

    assert ledger_mod.fetch_kalshi_rows(fetch) == []


# ---- recording: idempotence and model isolation ----------------------------

def model(version=VERSION, mean=30.0, stats=("points",)):
    def project(event, stat, names):
        return {n: {"player_id": i, "mean": mean} for i, n in enumerate(names, 1)}

    return ledger_mod.KalshiModel(
        version, {s: nba_stat_model.STATS[s].dispersion for s in stats}, project)


def test_rerunning_the_snapshot_adds_no_duplicate_rows(tmp_path):
    path = tmp_path / "ledger.csv"
    rows = one_per_game()
    first = ledger_mod.record_kalshi(rows, EVENTS, [model()], RECORDED_AT, path=path)
    assert first == {VERSION: 7}
    before = path.read_text(encoding="utf-8")
    again = ledger_mod.record_kalshi(
        rows, EVENTS, [model()], "2026-11-04T19:00:00+00:00", path=path)
    assert again == {VERSION: 0}
    assert path.read_text(encoding="utf-8") == before        # not a byte changed
    assert len(nba_paper.load_ledger(path)) == 7


def test_a_later_run_keeps_the_first_price_but_adds_a_newly_liquid_contract(tmp_path):
    path = tmp_path / "ledger.csv"
    early = rows_of(market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 25))
    ledger_mod.record_kalshi(early, EVENTS, [model()], RECORDED_AT, path=path)
    later = rows_of(
        market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 25,
               yes_bid="0.6000", yes_ask="0.6400", no_bid="0.3600", no_ask="0.4000"),
        market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 30))
    added = ledger_mod.record_kalshi(
        later, EVENTS, [model()], "2026-11-04T19:00:00+00:00", path=path)
    assert added == {VERSION: 1}
    saved = nba_paper.load_ledger(path).sort_values("line")
    assert list(saved["line"]) == [24.5, 29.5]
    assert saved["over_odds"].iloc[0] == -138                 # the early price stands


def test_kalshi_rows_do_not_collide_with_fanduel_rows_for_the_same_line(tmp_path):
    path = tmp_path / "ledger.csv"
    fanduel_line = [{"player": "Kevin Durant", "line": 24.5, "over_odds": -115,
                     "under_odds": -105}]
    fd_rows = nba_paper.build_ledger_rows(
        EVENTS[1], fanduel_line, {"Kevin Durant": {"player_id": 1, "mean": 30.0}},
        RECORDED_AT, "2026-11-04", model_version=VERSION)
    assert nba_paper.append_rows(fd_rows, path=path) == 1
    kalshi_rows = rows_of(market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 25))
    assert ledger_mod.record_kalshi(
        kalshi_rows, EVENTS, [model()], RECORDED_AT, path=path) == {VERSION: 1}
    assert sorted(nba_paper.load_ledger(path)["book"]) == ["fanduel", "kalshi"]


def test_a_broken_model_does_not_stop_the_others_or_raise(tmp_path):
    path = tmp_path / "ledger.csv"

    def broken(event, stat, names):
        raise RuntimeError("could not train")

    added = ledger_mod.record_kalshi(
        one_per_game(), EVENTS,
        [ledger_mod.KalshiModel("broken", {"points": 7.8}, broken), model("steady")],
        RECORDED_AT, path=path)
    assert added == {"broken": 0, "steady": 7}


def test_all_four_stats_are_recorded_for_one_game(tmp_path):
    path = tmp_path / "ledger.csv"
    rows = rows_of(
        market("KXNBAPTS", "MIN", "HOU", "DURANT", "Kevin Durant", 25),
        market("KXNBAREB", "MIN", "HOU", "GOBERT", "Rudy Gobert", 12),
        market("KXNBAAST", "MIN", "HOU", "THOMPSON", "Amen Thompson", 8),
        market("KXNBA3PT", "MIN", "HOU", "EDWARDS", "Anthony Edwards", 4))
    every = tuple(nba_stat_model.STATS)
    assert ledger_mod.record_kalshi(
        rows, EVENTS, [model(stats=every, mean=9.0)], RECORDED_AT, path=path) == {VERSION: 4}
    saved = nba_paper.load_ledger(path).set_index("stat")
    assert set(saved.index) == set(every)
    assert saved.loc["rebounds", "line"] == 11.5 and saved.loc["threes", "line"] == 3.5


# ---- the snapshot script ---------------------------------------------------

@pytest.fixture
def script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "nba_props_snapshot.py"
    spec = importlib.util.spec_from_file_location("nba_props_snapshot_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def heartbeat_file(script, tmp_path, monkeypatch):
    """Keep the tests' heartbeats out of the real data folder."""
    monkeypatch.setattr(script.job_health, "HEARTBEAT_PATH", tmp_path / "heartbeat.json")
    monkeypatch.setattr(script, "RETRY_WAIT_SECONDS", 0.0)          # no real waiting in tests
    return tmp_path / "heartbeat.json"


class Exploding:
    """Stands in for Models: fails the test if anything is built."""

    def __getattr__(self, name):
        raise AssertionError(f"models.{name} should not be touched")


def test_script_does_not_build_models_when_kalshi_has_nothing(script, monkeypatch):
    monkeypatch.setattr(script.nba_kalshi_ledger, "fetch_kalshi_rows", lambda: [])
    script.record_kalshi(EVENTS, Exploding())


def test_script_swallows_any_kalshi_failure(script, monkeypatch, caplog):
    def boom():
        raise RuntimeError("anything at all")

    monkeypatch.setattr(script.nba_kalshi_ledger, "fetch_kalshi_rows", boom)
    with caplog.at_level(logging.INFO):
        script.record_kalshi(EVENTS, Exploding())          # must not raise
    assert any("FanDuel snapshot is unaffected" in r.getMessage() for r in caplog.records)


def run_main(script, monkeypatch, tasks, *, remaining):
    order = []
    monkeypatch.setattr(script.sys, "argv", ["nba_props_snapshot.py"])
    monkeypatch.setattr(script.nba_props, "upcoming_events", lambda: EVENTS)
    monkeypatch.setattr(script.nba_props, "load_snapshots", lambda: None)
    monkeypatch.setattr(script.nba_props, "requests_remaining", lambda: remaining)
    monkeypatch.setattr(script.nba_snapshot_plan, "plan_snapshots", lambda *a, **k: tasks)

    def fetch(event):
        order.append(("fanduel_fetch", event["event_id"]))
        return {"fanduel": [], "draftkings": []}

    monkeypatch.setattr(script.nba_props, "fetch_event_books", fetch)
    monkeypatch.setattr(script.nba_props, "append_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(script, "record_lines", lambda *a, **k: {})
    monkeypatch.setattr(script, "record_alt_lines", lambda *a, **k: None)
    monkeypatch.setattr(script, "Models", lambda today: Exploding())
    monkeypatch.setattr(
        script, "record_kalshi",
        lambda events, models: order.append(("kalshi", [e["event_id"] for e in events])))
    monkeypatch.setattr(
        script, "archive_kalshi_closing",
        lambda events: order.append(("kalshi_close", [e["event_id"] for e in events])))
    monkeypatch.setattr(script, "log_price_gaps",
                        lambda events: order.append(("gaps", [e["event_id"] for e in events])))
    script.main()
    return order


def run_main_with_fetch(script, monkeypatch, tasks):
    """Like run_main, but keeps whatever fetch_event_books the test already installed."""
    monkeypatch.setattr(script.sys, "argv", ["nba_props_snapshot.py"])
    monkeypatch.setattr(script.nba_props, "upcoming_events", lambda: EVENTS)
    monkeypatch.setattr(script.nba_props, "load_snapshots", lambda: None)
    monkeypatch.setattr(script.nba_props, "requests_remaining", lambda: 300)
    monkeypatch.setattr(script.nba_snapshot_plan, "plan_snapshots", lambda *a, **k: tasks)
    monkeypatch.setattr(script, "Models", lambda today: Exploding())
    monkeypatch.setattr(script, "archive_kalshi_closing", lambda events: None)
    monkeypatch.setattr(script, "log_price_gaps", lambda events: 0)
    script.main()


def test_kalshi_follows_the_early_window_only_and_runs_after_fanduel(script, monkeypatch):
    plan = nba_snapshot_plan
    tasks = [plan.SnapshotTask(EVENTS[0], "early"), plan.SnapshotTask(EVENTS[1], "late"),
             plan.SnapshotTask(EVENTS[2], "early")]
    order = run_main(script, monkeypatch, tasks, remaining=300)
    assert order == [("fanduel_fetch", "e1"), ("fanduel_fetch", "e2"), ("fanduel_fetch", "e3"),
                     ("kalshi", ["e1", "e3"]), ("gaps", ["e1", "e3"]), ("kalshi_close", ["e2"])]


def test_kalshi_is_exempt_from_the_odds_api_reserve(script, monkeypatch):
    tasks = [nba_snapshot_plan.SnapshotTask(EVENTS[0], "early")]
    order = run_main(script, monkeypatch, tasks, remaining=script.nba_props.QUOTA_RESERVE)
    # FanDuel stopped on the reserve; Kalshi still ran, and the gaps were logged after it
    assert order == [("kalshi", ["e1"]), ("gaps", ["e1"])]


def test_a_cycle_with_only_late_snapshots_saves_kalshi_closing_prices_not_picks(script, monkeypatch):
    tasks = [nba_snapshot_plan.SnapshotTask(EVENTS[0], "late")]
    order = run_main(script, monkeypatch, tasks, remaining=300)
    assert order == [("fanduel_fetch", "e1"), ("kalshi_close", ["e1"])]


# ---- the heartbeat the job leaves behind ----------------------------------------------------------------

def beat(path):
    from edgefinder.data import job_health
    return job_health.load(path)["snapshot"]


def test_a_normal_run_reports_ok_with_how_many_snapshots_it_recorded(
        script, monkeypatch, heartbeat_file):
    tasks = [nba_snapshot_plan.SnapshotTask(EVENTS[0], "early"),
             nba_snapshot_plan.SnapshotTask(EVENTS[1], "late")]
    run_main(script, monkeypatch, tasks, remaining=300)
    assert beat(heartbeat_file) | {"ran_at": ""} == {
        "ran_at": "", "outcome": "ok", "detail": "2 of 2 due snapshots recorded"}


def test_a_run_with_nothing_due_still_reports_in(script, monkeypatch, heartbeat_file):
    run_main(script, monkeypatch, [], remaining=300)
    assert beat(heartbeat_file)["outcome"] == "nothing_due"


def test_stopping_on_the_request_reserve_is_ok_but_says_so(script, monkeypatch, heartbeat_file):
    tasks = [nba_snapshot_plan.SnapshotTask(EVENTS[0], "early")]
    run_main(script, monkeypatch, tasks, remaining=script.nba_props.QUOTA_RESERVE)
    result = beat(heartbeat_file)
    assert result["outcome"] == "ok" and "request reserve reached" in result["detail"]
    assert result["detail"].startswith("0 of 1")


def test_an_api_failure_before_anything_was_recorded_is_a_failed_run(
        script, monkeypatch, heartbeat_file):
    def broken(event):
        raise script.nba_props.PropsApiError("the odds service is down")

    tasks = [nba_snapshot_plan.SnapshotTask(EVENTS[0], "early")]
    monkeypatch.setattr(script.nba_props, "fetch_event_books", broken)
    run_main_with_fetch(script, monkeypatch, tasks)
    result = beat(heartbeat_file)
    assert result["outcome"] == "failed" and "odds service is down" in result["detail"]


# ---- the second book that rides along on the FanDuel request ----------------------------------------

DK_LINE = {"player": "A", "line": 21.5, "over_odds": -120, "under_odds": -105}
FD_LINE = {"player": "A", "line": 20.5, "over_odds": -110, "under_odds": -110}


def test_the_other_books_lines_are_archived_with_the_book_named(script, monkeypatch, caplog):
    saved = []
    monkeypatch.setattr(script.nba_props, "append_book_snapshot",
                        lambda event, phase, book, lines, fetched_at: saved.append(
                            (event["event_id"], phase, book, lines)))
    with caplog.at_level(logging.INFO):
        script.archive_other_books(EVENTS[0], "late", {"fanduel": [FD_LINE], "draftkings": [DK_LINE]},
                                   RECORDED_AT)
    assert saved == [("e1", "late", "draftkings", [DK_LINE])]
    assert any("1 players on both, 1 worth a look" in r.getMessage() for r in caplog.records)


def test_a_book_with_no_lines_writes_nothing(script, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("nothing should be archived")

    monkeypatch.setattr(script.nba_props, "append_book_snapshot", fail)
    script.archive_other_books(EVENTS[0], "early", {"fanduel": [FD_LINE], "draftkings": []},
                               RECORDED_AT)


def test_a_failure_archiving_the_other_book_never_stops_the_run(script, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(script.nba_props, "append_book_snapshot", boom)
    with caplog.at_level(logging.INFO):
        script.archive_other_books(EVENTS[0], "early", {"fanduel": [], "draftkings": [DK_LINE]},
                                   RECORDED_AT)                      # must not raise
    assert any("FanDuel snapshot is unaffected" in r.getMessage() for r in caplog.records)


def test_not_being_able_to_list_games_is_a_failed_run(script, monkeypatch, heartbeat_file):
    def broken():
        raise script.nba_props.PropsApiError("no key")

    monkeypatch.setattr(script.sys, "argv", ["nba_props_snapshot.py"])
    monkeypatch.setattr(script.nba_props, "upcoming_events", broken)
    with pytest.raises(SystemExit):
        script.main()
    assert beat(heartbeat_file)["outcome"] == "failed"
    assert "could not list games" in beat(heartbeat_file)["detail"]


# ---- other ledger readers --------------------------------------------------

def test_parlay_legs_ignore_kalshi_and_non_points_rows():
    line = [{"player": "Kevin Durant", "line": 24.5, "over_odds": -115, "under_odds": -105}]
    projection = {"Kevin Durant": {"player_id": 1, "mean": 30.0}}
    common = (EVENTS[1], line, projection, RECORDED_AT, "2026-11-04")
    ledger = pd.DataFrame(
        nba_paper.build_ledger_rows(*common, model_version=VERSION)
        + nba_paper.build_ledger_rows(*common, model_version=VERSION, book="kalshi")
        + nba_paper.build_ledger_rows(*common, model_version=VERSION, stat="rebounds"))
    rows = nba_parlay._over_under_rows(ledger, "2026-11-04", VERSION)
    assert len(rows) == 2          # the FanDuel points line, over and under


# ---- a blip on the odds service should not cost a whole cycle ----------------------------------------------

def test_a_failed_call_is_retried_and_the_pauses_are_taken(script):
    pauses, attempts = [], []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise script.nba_props.PropsApiError("Odds API returned HTTP 502")
        return ["games"]

    assert script.with_retries(flaky, attempts=3, wait=7.0, sleep=pauses.append) == ["games"]
    assert len(attempts) == 3 and pauses == [7.0, 7.0]


def test_the_last_error_surfaces_after_the_attempts_run_out(script):
    pauses = []

    def down():
        raise script.nba_props.PropsApiError("Odds API returned HTTP 502")

    with pytest.raises(script.nba_props.PropsApiError, match="502"):
        script.with_retries(down, attempts=3, wait=1.0, sleep=pauses.append)
    assert len(pauses) == 2                     # paused between the three tries, not after the last


def test_a_call_that_works_first_time_never_pauses(script):
    pauses = []
    assert script.with_retries(lambda: 5, sleep=pauses.append) == 5 and pauses == []


def test_other_errors_are_not_retried(script):
    pauses = []

    def bug():
        raise ValueError("a real bug")

    with pytest.raises(ValueError):
        script.with_retries(bug, sleep=pauses.append)
    assert pauses == []



def test_logging_price_gaps_writes_only_to_the_paths_given_and_never_fails_the_run(
        script, tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("anything")

    monkeypatch.setattr(script.price_gaps, "find_gaps", boom)
    assert script.log_price_gaps(EVENTS, tmp_path / "l.csv", tmp_path / "a.csv",
                                 tmp_path / "g.csv") == 0
    assert not (tmp_path / "g.csv").exists()


def test_logging_price_gaps_end_to_end_logs_tonights_gaps_once(script, tmp_path):
    import datetime as dt
    from edgefinder.tracking import gap_log, nba_alt, nba_paper
    future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    event = {"event_id": "e9", "commence_time": future, "away": "Miami Heat",
             "home": "Golden State Warriors"}
    when = dt.datetime.now(dt.timezone.utc).isoformat()
    tip_day = nba_snapshot_plan.tip_date(event)
    kalshi_row = {c: None for c in nba_paper.COLUMNS} | {
        "game_date": tip_day, "event_id": "e9", "commence_time": future, "away": event["away"],
        "home": event["home"], "player": "A", "player_id": 1, "line": 24.5, "over_odds": -150,
        "under_odds": 130, "fair_p_over": 0.6, "recorded_at": when, "stat": "points",
        "book": "kalshi", "model_version": "ewma-v1"}
    alt_row = {c: None for c in nba_alt.COLUMNS} | {
        "game_date": tip_day, "event_id": "e9", "away": event["away"], "home": event["home"],
        "player": "A", "player_id": 1, "threshold": 25, "over_odds": 100, "recorded_at": when,
        "model_version": "ewma-v1"}
    ledger_path, alt_path, log_path = tmp_path / "l.csv", tmp_path / "a.csv", tmp_path / "g.csv"
    nba_paper.save_ledger(pd.DataFrame([kalshi_row], columns=nba_paper.COLUMNS), ledger_path)
    nba_alt.save_ledger(pd.DataFrame([alt_row], columns=nba_alt.COLUMNS), alt_path)
    # FanDuel 25+ at +100 against Kalshi's 60%: 0.6 * 2 - 1 = +20%
    assert script.log_price_gaps([event], ledger_path, alt_path, log_path) == 1
    assert script.log_price_gaps([event], ledger_path, alt_path, log_path) == 0   # once only
    row = gap_log.load(log_path).iloc[0]
    assert (row["bet"], row["book"], row["status"]) == ("25+", "fanduel", "pending")
    assert row["edge_pct"] == pytest.approx(20.0)
