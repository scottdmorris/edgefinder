"""The +EV screen: each book's price against the other books' devigged consensus, and the paper
ledger that grades its flags. Made-up lines only; nothing here reads data/ or the network."""

import datetime as dt
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from edgefinder.api import app as api_app
from edgefinder.api import ev as ev_api
from edgefinder.api import service
from edgefinder.data import propline
from edgefinder.data.nba_snapshot_plan import tip_date
from edgefinder.tracking import ev_log, ev_screen

TIP = "2026-11-26T00:00:00Z"
BEFORE = dt.datetime(2026, 11, 25, 20, 0, tzinfo=dt.timezone.utc)
AFTER = dt.datetime(2026, 11, 26, 0, 5, tzinfo=dt.timezone.utc)


def row(book, over, under, player="Bam Adebayo", stat="points", line=18.5, fetched="2026-11-25T18:00:00+00:00",
        player_id="nba:1628389"):
    return {"fetched_at": fetched, "phase": "early", "event_id": "e1", "commence_time": TIP,
            "home": "Philadelphia 76ers", "away": "Miami Heat", "book": book, "stat": stat,
            "player": player, "player_id": player_id, "line": line, "over_odds": over,
            "under_odds": under}


# four books agree the over is a coin flip (-110/-110 each); one pays +120 on it
MARKET = [row("pinnacle", -110, -110), row("draftkings", -110, -110), row("betmgm", -110, -110),
          row("novig", -110, -110), row("fanduel", 120, -150)]


def flags(rows=MARKET, **kw):
    return ev_screen.screen(pd.DataFrame(rows), **kw)


def test_a_book_paying_more_than_the_others_fair_price_is_flagged():
    found = flags()
    assert len(found) == 1
    flag = found.iloc[0]
    assert (flag["book"], flag["side"], flag["odds"]) == ("fanduel", "Over", 120.0)
    assert flag["fair_p"] == pytest.approx(0.5)
    assert flag["fair_odds"] == 100
    assert flag["edge_pct"] == pytest.approx(10.0)          # 2.2 x 0.5 - 1
    assert flag["books"] == 4 and flag["game"] == "Miami Heat @ Philadelphia 76ers"


def test_the_flagged_book_is_left_out_of_its_own_fair_price():
    # with the +120 book itself in the average the fair over would drop below 0.5
    flag = flags().iloc[0]
    assert flag["fair_p"] == pytest.approx(0.5)


def test_identical_prices_are_not_flagged_because_the_margin_is_a_cost():
    assert flags([row(b, -110, -110) for b in ("a", "b", "c", "d", "e")]).empty


def test_a_line_needs_enough_other_books_on_the_same_number():
    assert flags(MARKET[2:]).empty                           # only two others
    assert len(flags(MARKET[2:], min_books=2)) == 1
    other_number = [*MARKET[:4], row("fanduel", 120, -150, line=19.5)]
    assert flags(other_number).empty


def test_pickem_apps_neither_count_nor_get_flagged():
    pickem = [row("prizepicks", 100, 100), row("pick6", 100, 100), row("underdog", 100, 100)]
    assert flags([*MARKET[:2], *pickem, row("fanduel", 120, -150)]).empty
    assert flags([*MARKET[:4], row("prizepicks", 150, 150)]).empty


def test_one_sided_prices_can_be_flagged_but_do_not_count_toward_fair():
    one_sided = [*MARKET[:4], row("fanduel", 120, None), row("bovada", None, -150)]
    found = flags(one_sided)
    assert list(found["book"]) == ["fanduel"] and found.iloc[0]["books"] == 4


def test_edges_too_big_to_trust_and_far_tails_are_left_out():
    assert flags([*MARKET[:4], row("fanduel", 300, -500)]).empty          # 100% "edge"
    longshot = [row(b, 400, -600) for b in "abcd"] + [row("fanduel", 520, -900)]
    assert flags(longshot).empty                                          # fair under 20%


def test_one_stale_book_does_not_move_the_fair_price_for_the_others():
    rows = [*MARKET[:4], row("stale", -400, 300), row("fanduel", 120, -150)]
    found = flags(rows)
    assert list(found["book"]) == ["fanduel"] and found.iloc[0]["fair_p"] == pytest.approx(0.5)


def test_weights_tilt_the_fair_price_toward_the_books_given_more_weight():
    rows = [row("pinnacle", -125, 105), row("b", -110, -110), row("c", -110, -110),
            row("d", -110, -110), row("fanduel", 120, -150)]
    plain = flags(rows).iloc[0]["fair_p"]
    tilted = flags(rows, weights={"pinnacle": 5.0}).iloc[0]["fair_p"]
    assert tilted > plain


def test_latest_keeps_each_games_newest_fetch_before_tip_without_pickem():
    rows = [*[r | {"fetched_at": "2026-11-25T18:00:00+00:00"} for r in MARKET],
            *[r | {"fetched_at": "2026-11-25T23:00:00+00:00"} for r in MARKET[:3]],
            row("prizepicks", 100, 100, fetched="2026-11-25T23:00:00+00:00"),
            row("pinnacle", -200, 150, fetched="2026-11-26T00:10:00+00:00")]      # after tip
    table = ev_screen.latest(pd.DataFrame(rows))
    assert set(table["fetched_at"]) == {"2026-11-25T23:00:00+00:00"}
    assert set(table["book"]) == {"pinnacle", "draftkings", "betmgm"}
    assert ev_screen.latest(pd.DataFrame(rows), now=AFTER).empty
    assert ev_screen.latest(None).empty


def test_book_names_read_well_even_for_books_not_listed():
    assert ev_screen.book_name("polymarket_us") == "Polymarket"
    assert ev_screen.book_name("new_book") == "New Book"


# ---- the paper ledger ---------------------------------------------------------------------------

def logged(now=BEFORE, rows=MARKET):
    return ev_log.rows_to_log(flags(rows), now, tip_date)


def test_flags_are_logged_with_the_nba_id_and_game_date_before_tip_only():
    [entry] = logged()
    assert entry["player_id"] == 1628389 and entry["game_date"] == "2026-11-25"
    assert (entry["bet"], entry["status"], entry["stat"]) == ("Over 18.5", "pending", "points")
    assert set(ev_log.COLUMNS) <= set(entry)
    assert logged(now=AFTER) == []
    no_id = [*MARKET[:4], row("fanduel", 120, -150, player_id=None)]
    assert logged(rows=no_id) == []


def test_a_flag_is_logged_once_and_the_first_price_stays(tmp_path):
    path = tmp_path / "ev.csv"
    assert ev_log.append(logged(), path) == 1
    better = [*MARKET[:4], row("fanduel", 130, -160)]
    assert ev_log.append(logged(rows=better), path) == 0
    saved = ev_log.load(path)
    assert len(saved) == 1 and saved.iloc[0]["odds"] == 120.0
    assert list(saved.columns) == ev_log.COLUMNS


def games(pid=1628389, pts=21.0, reb=4.0, date="2026-11-25"):
    """A complete two-team box score, so a missing player could be voided."""
    def player(p, team, opp, **stats):
        return {"player_id": p, "game_id": "g1", "game_date": pd.Timestamp(date), "team": team,
                "opponent": opp, "minutes": 48.0, "pts": 0.0, "reb": 0.0, "ast": 0.0,
                "fg3m": 0.0} | stats
    rows = [player(pid, "MIA", "PHI", pts=pts, reb=reb)]
    rows += [player(900 + i, "MIA", "PHI") for i in range(4)]
    rows += [player(800 + i, "PHI", "MIA") for i in range(5)]
    return pd.DataFrame(rows)


def test_flags_are_graded_by_their_own_stat_at_a_flat_unit():
    rebounds = [r | {"stat": "rebounds", "line": 5.5} for r in MARKET]
    log = pd.DataFrame(logged() + logged(rows=rebounds), columns=ev_log.COLUMNS)
    settled = ev_log.settle(log, games(), dt.date(2026, 11, 26)).set_index("stat")
    assert settled.loc["points", "result"] == "win" and settled.loc["points", "actual"] == 21.0
    assert settled.loc["points", "pnl_units"] == pytest.approx(1.2)
    assert settled.loc["rebounds", "result"] == "loss" and settled.loc["rebounds", "pnl_units"] == -1.0


def test_a_player_who_did_not_play_is_void_once_his_games_logs_are_complete():
    log = pd.DataFrame(logged(), columns=ev_log.COLUMNS)
    settled = ev_log.settle(log, games(pid=1), dt.date(2026, 11, 26))
    assert settled.iloc[0]["status"] == "void"
    still = ev_log.settle(log, games(pid=1), dt.date(2026, 11, 25))
    assert still.iloc[0]["status"] == "pending"


def test_closing_value_is_against_every_books_fair_close():
    log = pd.DataFrame(logged(), columns=ev_log.COLUMNS)
    late = pd.DataFrame([r | {"phase": "late", "fetched_at": "2026-11-25T23:30:00+00:00"}
                         for r in MARKET[:4]] + [row("prizepicks", 300, -900) | {"phase": "late"}])
    closed = ev_log.attach_closing(log, late)
    assert closed.iloc[0]["clv_novig_pct"] == pytest.approx(10.0)      # 2.2 x 0.5 - 1
    assert ev_log.attach_closing(log, None).iloc[0]["clv_novig_pct"] is None


def test_summary_reports_overall_and_by_stat():
    log = pd.DataFrame(logged(), columns=ev_log.COLUMNS)
    s = ev_log.summary(ev_log.settle(log, games(), dt.date(2026, 11, 26)))
    assert s["all"]["record"] == "1-0" and s["by_stat"]["points"]["units"] == pytest.approx(1.2)


# ---- the snapshot job and the API -------------------------------------------------------------

def test_the_snapshot_job_logs_flags_and_never_fails_on_them(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "nba_props_snapshot.py"
    spec = importlib.util.spec_from_file_location("snapshot_under_test_ev", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    tip = "2099-11-26T00:00:00Z"
    event = {"event_id": "e1", "commence_time": tip, "home": "Philadelphia 76ers", "away": "Miami Heat"}
    def listing(book, over, under):
        outcomes = [{"name": side, "description": "Bam Adebayo", "price": price, "point": 18.5,
                     "player_id": "nba:1628389"} for side, price in (("Over", over), ("Under", under))]
        return {"key": book, "markets": [{"key": "player_points", "line_type": "main",
                                          "outcomes": outcomes}]}
    game = {"id": 1, "commence_time": tip, "home_team": event["home"], "away_team": event["away"],
            "bookmakers": [listing(r["book"], r["over_odds"], r["under_odds"]) for r in MARKET]}
    task = type("Task", (), {"event": event, "phase": "early"})()
    assert script.log_ev_flags([game], [task], "2099-11-25T18:00:00+00:00", tmp_path / "ev.csv") == 1
    assert ev_log.load(tmp_path / "ev.csv").iloc[0]["book"] == "fanduel"
    assert script.log_ev_flags([{"nonsense": 1}], [task], "t", tmp_path / "ev.csv") == 0   # logged, not raised


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    service.clear_cache()
    monkeypatch.setattr(service, "today", lambda: dt.date(2026, 11, 25))
    monkeypatch.setattr(service, "now", lambda: BEFORE)
    monkeypatch.setattr(ev_api, "load_snapshots", lambda: pd.DataFrame(MARKET))
    monkeypatch.setattr(ev_api, "load_log", lambda: pd.DataFrame(logged(), columns=ev_log.COLUMNS))
    yield TestClient(api_app.app)
    service.clear_cache()


def test_the_ev_route_lists_book_line_price_fair_price_and_edge(client):
    body = client.get("/api/ev").json()
    assert body["date"] == "2026-11-25" and body["flagged"] == 1 and body["books"] == 5
    [line] = body["lines"]
    assert (line["book_name"], line["bet"], line["odds"], line["fair_odds"]) == (
        "FanDuel", "Over 18.5 points", 120, 100)
    assert line["edge_pct"] == 10.0 and line["fair_pct"] == 50.0 and line["books"] == 4
    assert line["photo"].endswith("/1628389.png")
    assert body["record"]["logged"] == 1 and body["record"]["record"] == "0-0"


def test_the_ev_route_is_empty_on_another_day_and_rejects_a_bad_date(client):
    assert client.get("/api/ev", params={"date": "2026-11-27"}).json()["lines"] == []
    assert client.get("/api/ev", params={"date": "tonight"}).status_code == 404


def test_the_ev_route_hides_games_that_have_started(client, monkeypatch):
    monkeypatch.setattr(service, "now", lambda: AFTER)
    assert client.get("/api/ev").json()["lines"] == []


def test_load_snapshots_reads_every_book(tmp_path, monkeypatch):
    path = tmp_path / "lines.csv"
    pd.DataFrame([r | {"propline_event_id": 1, "changed_at": None} for r in MARKET]).to_csv(path, index=False)
    monkeypatch.setattr(propline, "LINES_PATH", path)
    service.clear_cache()
    assert set(ev_api.load_snapshots()["book"]) == {r["book"] for r in MARKET}
    service.clear_cache()
