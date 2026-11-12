"""The web app's API, run against a small made-up ledger (no files, no network)."""

import datetime as dt

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from edgefinder.api import app as api_app
from edgefinder.api import record as record_api
from edgefinder.api import service
from edgefinder.data import job_health
from edgefinder.tracking import gap_log, nba_alt, nba_paper

DAY = "2026-11-04"
WHEN = "2026-11-04T17:00:00+00:00"
GAMES = [
    {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
     "home": "Boston Celtics", "away": "Milwaukee Bucks"},
    {"event_id": "e2", "commence_time": "2026-11-05T00:30:00Z",
     "home": "New York Knicks", "away": "Chicago Bulls"},
]
PLAYERS = [("Jaylen Brown", 1, 27.0, GAMES[0]), ("Jalen Brunson", 2, 34.0, GAMES[1])]


def _ledger() -> pd.DataFrame:
    rows = []
    for name, pid, mean, event in PLAYERS:
        line = {"player": name, "line": 24.5, "over_odds": -110, "under_odds": -110}
        rows += nba_paper.build_ledger_rows(event, [line], {name: {"player_id": pid, "mean": mean}},
                                            WHEN, DAY, model_version="minutes-v1", dispersion=7.8)
    return pd.DataFrame(rows, columns=nba_paper.COLUMNS)


def _alt() -> pd.DataFrame:
    rows = []
    for name, pid, mean, event in PLAYERS:
        line = {"player": name, "line": 24.5, "over_odds": 130}
        rows += nba_alt.build_alt_rows(event, [line], {name: {"player_id": pid, "mean": mean}},
                                       WHEN, DAY, model_version="minutes-v1", dispersion=7.8)
    return pd.DataFrame(rows, columns=nba_alt.COLUMNS)


@pytest.fixture
def client(monkeypatch):
    service.clear_cache()
    monkeypatch.setattr(service, "today", lambda: dt.date.fromisoformat(DAY))
    monkeypatch.setattr(service, "load_ledger", _ledger)
    monkeypatch.setattr(service, "load_alt", _alt)
    monkeypatch.setattr(service, "load_games", pd.DataFrame)
    monkeypatch.setattr(job_health, "load", lambda: {})
    # the record's tamper log and gap log are real files: keep the tests away from them
    monkeypatch.setattr(record_api, "chain", lambda: {"started": False})
    monkeypatch.setattr(gap_log, "load", pd.DataFrame)
    yield TestClient(api_app.app)
    service.clear_cache()


def test_health_reports_both_jobs(client):
    body = client.get("/api/health").json()
    assert set(body) == {"snapshot", "settle"}
    assert {"level", "text"} <= set(body["snapshot"])


def test_days_lists_each_game_day_with_a_label(client):
    days = client.get("/api/days").json()
    assert [d["date"] for d in days] == [DAY]
    assert days[0]["label"]


def test_board_defaults_to_the_latest_day_and_lists_every_leg(client):
    board = client.get("/api/board").json()
    assert board["date"] == DAY and board["book"] == "fanduel" and board["model"] == "minutes-v1"
    assert board["summary"]["games"] == 2
    assert {leg["player"] for leg in board["legs"]} == {"Jaylen Brown", "Jalen Brunson"}
    leg = board["legs"][0]
    assert {"id", "odds", "market_pct", "model_pct", "photo", "game_short", "bet"} <= set(leg)
    assert leg["projection"] in (27.0, 34.0)
    assert leg["projection_model"] == "Minutes"
    assert board["default_style"] in board["styles"]


def _steady_logs() -> pd.DataFrame:
    """Brown scored 25+ in 19 of his last 20 games; Brunson has only played five."""
    rows = []
    for pid, count in ((1, 24), (2, 5)):
        for n in range(count):
            day = pd.Timestamp("2026-10-01") + pd.Timedelta(days=n)
            pts = 10 if n in (0, 1, 2, 3, 12) else 30        # four early misses fall out of the 20
            rows.append({"player_id": pid, "game_date": day, "pts": pts, "reb": 5, "ast": 4,
                         "fg3m": 2, "minutes": 34.0, "season": "2026-27"})
    rows.append({"player_id": 1, "game_date": pd.Timestamp(DAY), "pts": 0, "reb": 0, "ast": 0,
                 "fg3m": 0, "minutes": 30.0, "season": "2026-27"})       # tonight: must not count
    return pd.DataFrame(rows)


def test_steady_lists_legs_a_player_nearly_always_reaches_with_the_price(client, monkeypatch):
    monkeypatch.setattr(service, "load_games", _steady_logs)
    monkeypatch.setattr(service, "_averages", dict)
    board = client.get("/api/board").json()
    assert [s["player"] for s in board["steady"]] == ["Jaylen Brown"]      # one leg, not three
    steady = board["steady"][0]
    assert (steady["hits"], steady["games"], steady["hit_pct"]) == (19, 20, 95.0)
    assert steady["threshold"] == 25 and steady["odds"] == 130             # the better price
    assert steady["price_pct"] == pytest.approx(43.5, abs=0.1)
    leg = next(leg for leg in board["legs"] if leg["id"] == steady["leg_id"])
    assert leg["player"] == "Jaylen Brown" and leg["side"] != "Under"


def test_steady_is_empty_without_game_logs(client):
    assert client.get("/api/board").json()["steady"] == []


def test_an_unknown_model_falls_back_to_one_that_has_lines(client):
    assert client.get("/api/board", params={"model": "nope"}).json()["model"] == "minutes-v1"


def test_a_day_without_lines_is_a_404(client):
    response = client.get("/api/board", params={"date": "2020-01-01"})
    assert response.status_code == 404
    assert "2020-01-01" in response.json()["detail"]


def test_an_unknown_style_is_a_404(client):
    assert client.get("/api/ideas", params={"style": "Reckless"}).status_code == 404


def test_ideas_only_use_legs_from_the_board(client):
    board = client.get("/api/board").json()
    ids = {leg["id"] for leg in board["legs"]}
    for style in board["styles"]:
        for idea in client.get("/api/ideas", params={"style": style}).json():
            assert set(idea["legs"]) <= ids
            assert 0 < idea["chance_pct"] <= 100


def test_a_slip_is_priced_with_payout_and_chance(client):
    legs = client.get("/api/board").json()["legs"]
    over = [leg["id"] for leg in legs if leg["side"] == "Over"][:2]
    body = client.post("/api/slip", json={"legs": over, "stake": 10}).json()
    assert body["legs"] == 2
    assert 0 < body["chance_pct"] < 100
    assert body["to_win"] > 10  # two -110 legs pay more than even money
    assert body["total_return"] == pytest.approx(body["to_win"] + 10, abs=0.01)
    assert "\\$" not in body["verdict"]


def test_an_empty_slip_prices_to_nothing(client):
    assert client.post("/api/slip", json={"legs": [], "stake": 10}).json() == {"legs": 0}


def test_a_slip_with_an_unknown_leg_is_a_404(client):
    assert client.post("/api/slip", json={"legs": [99999], "stake": 10}).status_code == 404


@pytest.mark.parametrize("payload", [
    {"legs": [0], "stake": -1},
    {"legs": list(range(13)), "stake": 10},
    {"legs": [0], "stake": 1_000_000},
])
def test_a_bad_slip_request_is_rejected(client, payload):
    assert client.post("/api/slip", json=payload).status_code == 422


def test_built_files_are_served_but_nothing_outside_the_build(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "logo.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("nope")
    assert api_app.web_file(dist, "logo.svg") == (dist / "logo.svg").resolve()
    assert api_app.web_file(dist, "../secret.txt") is None
    assert api_app.web_file(dist, str(tmp_path / "secret.txt")) is None
    assert api_app.web_file(dist, "assets") is None      # a folder, not a file
    assert api_app.web_file(dist, "") is None


# ---- live -----------------------------------------------------------------------------------------

from edgefinder.api import live as live_api  # noqa: E402
from edgefinder.data import nba_live  # noqa: E402
from edgefinder.data.nba_live import GameDetail, LiveGame, Play, PlayerLine, Shot  # noqa: E402


def _game(status=nba_live.LIVE, game_id="g1", away="MIL", home="BOS"):
    return LiveGame(game_id=game_id, status=status, status_text="2nd Qtr", period=2,
                    clock="5:00", away=away, home=home, away_score=40, home_score=44,
                    away_timeouts=3, home_timeouts=2, home_bonus=True)


def _detail():
    players = {1: PlayerLine(player_id=1, name="Jaylen Brown", team="BOS", points=18,
                             rebounds=4, assists=2, minutes=20.0, played=True, on_court=True,
                             starter=True, fouls=4),
               2: PlayerLine(player_id=2, name="Bench Guy", team="MIL", points=2, rebounds=1,
                             assists=0, minutes=6.0, played=True, on_court=False)}
    plays = [Play(order=1, period="Q2", clock="5:30", team="BOS", text="Brown 3PT", score="",
                  away_score=40, home_score=46),
             Play(order=2, period="Q2", clock="5:10", team="MIL", text="Free throw", score="",
                  away_score=41, home_score=46)]
    shots = [Shot(team="BOS", player="Jaylen Brown", made=True, x=10.0, y=50.0, period=2,
                  distance=24.0, is_three=True, description="")]
    return GameDetail(players=players, team_stats={"BOS": {"foulsPersonal": 9}, "MIL": {}},
                      period_scores={"MIL": [20, 20], "BOS": [24, 20]}, shots=shots, plays=plays)


@pytest.fixture
def feed(client, monkeypatch):
    games = [_game(nba_live.FINAL, "g0"), _game(), _game(nba_live.SCHEDULED, "g2", "NYK", "CHI")]
    monkeypatch.setattr(nba_live, "fetch_games", lambda: games)
    monkeypatch.setattr(nba_live, "fetch_detail", lambda gid, a, h: _detail())
    monkeypatch.setattr(nba_live, "fetch_box", lambda gid: _detail().players)
    return client


def test_live_games_come_on_now_first_with_the_score_from_the_latest_play(feed):
    games = feed.get("/api/live").json()
    assert [g["state"] for g in games] == ["live", "upcoming", "final"]
    live = games[0]
    assert (live["away"]["score"], live["home"]["score"]) == (41, 46)   # the play, not the board
    assert live["home"]["fouls"] == 9 and live["home"]["bonus"] is True
    assert live["away"]["timeouts"] == 3


def test_a_live_game_opens_with_quarters_shots_leaders_plays_and_box(feed):
    detail = feed.get("/api/live/g1").json()["detail"]
    assert detail["quarters"]["columns"][-1] == "Total"
    assert detail["plays"][0]["order"] == 2                              # newest first
    assert detail["shots"][0]["x"] == 90.0                               # home shoots right
    assert detail["foul_trouble"] == [{"name": "Jaylen Brown", "fouls": 4, "team": "BOS"}]
    assert detail["box"]["BOS"]["starters"][0]["Player"] == "Jaylen Brown"
    assert detail["box"]["BOS"]["starters"][0]["on_court"] is True
    assert {l["stat"] for l in detail["leaders"]} == {"Points", "Rebounds", "Assists"}


def test_a_game_that_has_not_started_has_no_detail(feed):
    assert feed.get("/api/live/g2").json()["detail"] is None


def test_live_receipt_times_are_cached_source_times_not_browser_request_times(feed):
    first = feed.get("/api/live").json()
    second = feed.get("/api/live").json()
    assert first[0]["received_at"] == second[0]["received_at"]
    assert first[0]["detail_received_at"] == second[0]["detail_received_at"]
    assert dt.datetime.fromisoformat(first[0]["received_at"]).tzinfo is not None
    assert first[0]["detail_available"] is True
    upcoming = next(game for game in first if game["state"] == "upcoming")
    assert upcoming["detail_received_at"] is None


def test_a_failed_game_detail_keeps_the_scoreboard_and_reports_unavailability(feed, monkeypatch):
    def down(*args):
        raise nba_live.LiveDataError("Game feed unavailable")
    monkeypatch.setattr(nba_live, "fetch_detail", down)
    response = feed.get("/api/live")
    assert response.status_code == 200
    game = response.json()[0]
    assert game["state"] == "live" and game["received_at"]
    assert game["detail_available"] is False and game["detail_received_at"] is None


def test_an_unknown_game_is_a_404(feed):
    assert feed.get("/api/live/zzz").status_code == 404


def test_the_live_feed_being_down_is_a_503_not_a_crash(client, monkeypatch):
    def down():
        raise nba_live.LiveDataError("NBA's live feed is down")
    monkeypatch.setattr(nba_live, "fetch_games", down)
    response = client.get("/api/live")
    assert response.status_code == 503 and "down" in response.json()["detail"]


def test_an_empty_slip_tracks_to_nothing(feed):
    assert feed.post("/api/live/track", json={"legs": []}).json()["legs"] == []


def test_a_slip_leg_with_no_game_tonight_is_not_started(feed):
    leg = feed.get("/api/board").json()["legs"][0]["id"]
    body = feed.post("/api/live/track", json={"legs": [leg]}).json()
    assert body["status"] == "Not started"
    assert body["legs"][0]["id"] == leg


# ---- record ---------------------------------------------------------------------------------------

def test_the_record_is_empty_before_any_picks(client, monkeypatch):
    monkeypatch.setattr(service, "load_ledger",
                        lambda: pd.DataFrame(columns=nba_paper.COLUMNS))
    assert client.get("/api/record").json() == {"empty": True}


def test_the_record_counts_locked_picks_and_splits_by_book(client):
    body = client.get("/api/record").json()
    assert body["empty"] is False
    assert body["integrity"]["after_tip"] == 0
    assert body["integrity"]["picks"] >= 1
    assert [m["id"] for m in body["models"]] == ["minutes-v1"]
    assert all({"day", "player", "bet", "locked", "result"} <= set(r) for r in body["log"])


# ---- players and picks ----------------------------------------------------------------------------

def _logs() -> pd.DataFrame:
    rows = []
    for day in range(1, 13):
        rows.append({"player_id": 77, "player_name": "Luka Dončić", "team_id": 10, "team": "LAL",
                     "game_id": f"g{day}", "game_date": pd.Timestamp(f"2026-10-{day + 10:02d}"),
                     "matchup": "LAL vs. GSW", "wl": "W", "minutes": 35.0, "pts": 20 + day,
                     "reb": 8, "ast": 9, "fg3m": 3, "stl": 1, "blk": 0, "tov": 3, "fga": 20,
                     "fta": 8, "is_home": day % 2 == 0, "opponent": "GSW", "season": "2026-27"})
    return pd.DataFrame(rows)


@pytest.fixture
def logs(client, monkeypatch):
    monkeypatch.setattr(service, "load_games", _logs)
    return client


def test_the_player_list_has_everyone_with_plain_letters_for_search(logs):
    (player,) = logs.get("/api/players").json()
    assert player == {"id": 77, "name": "Luka Dončić", "team": "LAL", "plain": "Luka Doncic"}


def test_a_player_profile_has_averages_and_games_newest_first(logs):
    body = logs.get("/api/players/77").json()
    assert body["season_games"] == 12 and body["averages"]["pts"] == 26.5
    assert body["games"][0]["date"] == "2026-10-22" and body["games"][0]["pts"] == 32
    assert body["tonight"] is None              # the made-up ledger has no line for 77


def test_an_unknown_player_is_a_404(logs):
    assert logs.get("/api/players/999").status_code == 404


def test_the_player_list_is_empty_without_game_logs(client):
    assert client.get("/api/players").json() == []


def test_picks_list_each_line_with_every_model_and_the_liked_bets(client):
    body = client.get("/api/picks").json()
    assert body["date"] == DAY
    assert {line["player"] for line in body["lines"]} == {"Jaylen Brown", "Jalen Brunson"}
    assert all(line["models"][0]["id"] == "minutes-v1" for line in body["lines"])
    assert [p["player"] for p in body["liked"]] == ["Jalen Brunson"]     # 34 projected vs 24.5


def test_picks_for_a_day_without_lines_is_a_404(client):
    assert client.get("/api/picks", params={"date": "2020-01-01"}).status_code == 404


def test_saved_quote_ids_survive_new_players_and_row_reordering(client, monkeypatch):
    before = client.get("/api/board").json()["legs"]
    ledger = _ledger()
    added = ledger.iloc[[0]].copy()
    added["player"], added["player_id"] = "Aaron Example", 999
    monkeypatch.setattr(service, "load_ledger",
                        lambda: pd.concat([added, ledger.iloc[::-1]], ignore_index=True))
    service.clear_cache()
    after = {leg["id"]: leg for leg in client.get("/api/board").json()["legs"]}
    for leg in before:
        assert after[leg["id"]] == leg
        assert 0 <= leg["id"] < 2**53


def test_saved_selection_survives_a_price_move_and_shows_the_new_price(client, monkeypatch):
    before = client.get("/api/board").json()["legs"]
    leg = next(l for l in before if l["side"] == "Over")
    changed = _ledger()
    changed.loc[changed.player_id == leg["player_id"], "over_odds"] = 125
    monkeypatch.setattr(service, "load_ledger", lambda: changed)
    service.clear_cache()
    after = {l["id"]: l for l in client.get("/api/board").json()["legs"]}
    assert after[leg["id"]]["odds"] == 125          # the same bet, at its new price
    assert client.post("/api/slip", json={"legs": [leg["id"]]}).status_code == 200


def test_a_bet_that_left_the_board_is_rejected_not_repriced(client, monkeypatch):
    leg = next(l for l in client.get("/api/board").json()["legs"] if l["side"] == "Under")
    gone = _ledger()
    monkeypatch.setattr(service, "load_ledger", lambda: gone[gone.player_id != leg["player_id"]])
    service.clear_cache()
    response = client.post("/api/slip", json={"legs": [leg["id"]]})
    assert response.status_code == 404
    assert "Refresh" in response.json()["detail"]


def test_old_slip_cannot_be_graded_against_todays_matchup(feed, monkeypatch):
    leg = feed.get("/api/board").json()["legs"][0]["id"]
    monkeypatch.setattr(service, "today", lambda: dt.date(2026, 11, 12))
    response = feed.post("/api/live/track", json={"date": DAY, "legs": [leg]})
    assert response.status_code == 422
    assert "cannot be inferred" in response.json()["detail"]


def test_kalshi_only_ledger_is_not_an_empty_record(client, monkeypatch):
    monkeypatch.setattr(service, "load_ledger", lambda: _ledger().assign(book="kalshi"))
    result = client.get("/api/record")
    assert result.status_code == 200
    assert result.json()["empty"] is False
    assert result.json()["models"] == []  # FanDuel models stay scoped to FanDuel


def test_old_positional_leg_ids_are_rejected(client):
    assert client.post("/api/slip", json={"legs": [0]}).status_code == 404


def test_a_live_game_takes_its_period_from_the_latest_play_not_the_lagging_scoreboard():
    from edgefinder.api import live
    game = nba_live.LiveGame("1", nba_live.LIVE, "Q1", 1, "0:00", "MIL", "BOS", 0, 0)
    assert live.freshest(game, _detail()).period == 2
    assert live._period_number("OT2") == 6
