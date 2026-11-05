"""Checks on the prop-line fetchers (with the network faked), the parsers and
the snapshot archive. Nothing here touches the real API, cache or data folder."""

import pandas as pd
import pytest
import requests

from edgefinder.data import nba_props

SECRET = "SECRET-KEY-123"
EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}


class FakeResponse:
    def __init__(self, payload=None, status=200, headers=None):
        self._payload, self.status_code = payload, status
        self.headers = headers or {}
        self.ok = status < 400

    def json(self):
        return self._payload


@pytest.fixture
def api(monkeypatch):
    """Fake the key, the HTTP call and the quota cache; record what was requested."""
    calls, quota = [], {}
    state = {"response": FakeResponse([]), "key": SECRET, "raises": None}
    monkeypatch.setattr(nba_props.odds_api, "get_api_key", lambda: state["key"])

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params, "timeout": timeout})
        if state["raises"]:
            raise state["raises"]
        return state["response"]

    monkeypatch.setattr(nba_props.requests, "get", fake_get)
    monkeypatch.setattr(nba_props.cache, "put", lambda key, value: quota.update({key: value}))
    monkeypatch.setattr(nba_props.odds_api, "get_quota", lambda: quota.get("odds_api_quota"))
    state.update(calls=calls, quota=quota)
    return state


# ---- HTTP wrapper ----------------------------------------------------------------------------------

def test_no_api_key_is_a_clear_error_and_no_request_is_made(api):
    api["key"] = None
    with pytest.raises(nba_props.PropsApiError, match="No Odds API key"):
        nba_props.upcoming_events()
    assert api["calls"] == []


def test_a_network_failure_never_leaks_the_key(api):
    api["raises"] = requests.ConnectionError(f"failed for https://x/?apiKey={SECRET}")
    with pytest.raises(nba_props.PropsApiError) as caught:
        nba_props.upcoming_events()
    assert SECRET not in str(caught.value)
    assert "ConnectionError" in str(caught.value)
    assert caught.value.__cause__ is None             # `from None`: the URL is not chained either


def test_a_timeout_is_also_scrubbed(api):
    api["raises"] = requests.Timeout(f"timed out calling ?apiKey={SECRET}")
    with pytest.raises(nba_props.PropsApiError) as caught:
        nba_props.fetch_event_lines(EVENT)
    assert SECRET not in str(caught.value) and "Timeout" in str(caught.value)


@pytest.mark.parametrize("status", [401, 422, 429, 500])
def test_http_errors_report_the_status_without_the_url(api, status):
    api["response"] = FakeResponse(status=status)
    with pytest.raises(nba_props.PropsApiError) as caught:
        nba_props.upcoming_events()
    assert f"HTTP {status}" in str(caught.value) and SECRET not in str(caught.value)


def test_the_key_goes_in_the_params_and_the_timeout_is_set(api):
    nba_props.upcoming_events()
    call = api["calls"][0]
    assert call["params"]["apiKey"] == SECRET
    assert call["timeout"] == nba_props.odds_api.REQUEST_TIMEOUT
    assert call["url"].endswith("/sports/basketball_nba/events")


def test_quota_headers_are_stored_when_present(api):
    api["response"] = FakeResponse([], headers={"x-requests-remaining": "412",
                                                "x-requests-used": "88"})
    nba_props.upcoming_events()
    assert api["quota"]["odds_api_quota"] == {"remaining": "412", "used": "88"}


def test_nothing_is_stored_when_the_quota_header_is_absent(api):
    nba_props.upcoming_events()
    assert api["quota"] == {}


def test_a_failed_request_does_not_overwrite_the_quota(api):
    api["response"] = FakeResponse(status=500, headers={"x-requests-remaining": "1"})
    with pytest.raises(nba_props.PropsApiError):
        nba_props.upcoming_events()
    assert api["quota"] == {}


# ---- remaining requests -------------------------------------------------------------------------------

@pytest.mark.parametrize("stored, expected", [
    ({"remaining": "412", "used": "88"}, 412),
    ({"remaining": 7}, 7),
    (None, None),
    ({}, None),
    ({"remaining": "lots"}, None),
])
def test_requests_remaining(api, stored, expected):
    api["quota"]["odds_api_quota"] = stored
    assert nba_props.requests_remaining() == expected


# ---- the endpoints -------------------------------------------------------------------------------------------

def test_upcoming_events_are_reshaped(api):
    api["response"] = FakeResponse([
        {"id": "abc", "commence_time": "2026-11-05T00:00:00Z", "home_team": "Detroit Pistons",
         "away_team": "Philadelphia 76ers", "sport_key": "ignored"}])
    assert nba_props.upcoming_events() == [EVENT | {"event_id": "abc"}]


def test_no_events_is_an_empty_list(api):
    api["response"] = FakeResponse([])
    assert nba_props.upcoming_events() == []


def player_payload(market, outcomes):
    return {"bookmakers": [{"key": "fanduel", "markets": [{"key": market, "outcomes": outcomes}]}]}


def test_event_lines_ask_for_one_market_from_one_book_in_american_odds(api):
    api["response"] = FakeResponse(player_payload("player_points", [
        {"name": "Over", "description": "A", "price": -110, "point": 20.5},
        {"name": "Under", "description": "A", "price": -110, "point": 20.5}]))
    lines = nba_props.fetch_event_lines(EVENT)
    params = api["calls"][0]["params"]
    assert params["markets"] == "player_points" and params["bookmakers"] == "fanduel"
    assert params["oddsFormat"] == "american" and params["regions"] == "us"
    assert api["calls"][0]["url"].endswith("/sports/basketball_nba/events/e1/odds")
    assert lines == [{"player": "A", "line": 20.5, "over_odds": -110, "under_odds": -110}]


def test_alt_lines_ask_for_the_alternate_market(api):
    api["response"] = FakeResponse(player_payload("player_points_alternate", [
        {"name": "Over", "description": "A", "price": 450, "point": 29.5}]))
    lines = nba_props.fetch_alt_lines(EVENT)
    assert api["calls"][0]["params"]["markets"] == "player_points_alternate"
    assert lines == [{"player": "A", "line": 29.5, "over_odds": 450}]


# ---- parsing ---------------------------------------------------------------------------------------------------

def test_alt_parser_keeps_only_over_prices_from_fanduel():
    payload = {"bookmakers": [
        {"key": "other", "markets": [{"key": "player_points_alternate", "outcomes": [
            {"name": "Over", "description": "Z", "price": 100, "point": 9.5}]}]},
        {"key": "fanduel", "markets": [
            {"key": "player_points", "outcomes": [
                {"name": "Over", "description": "WrongMarket", "price": 100, "point": 9.5}]},
            {"key": "player_points_alternate", "outcomes": [
                {"name": "Over", "description": "A", "price": 450, "point": 29.5},
                {"name": "Under", "description": "A", "price": -700, "point": 29.5},
                {"name": "Over", "description": None, "price": 100, "point": 9.5},
                {"name": "Over", "description": "NoPoint", "price": 100},
                {"name": "Over", "description": "NoPrice", "point": 14.5}]}]}]}
    assert nba_props.parse_alt_lines(payload) == [
        {"player": "A", "line": 29.5, "over_odds": 450},
        {"player": "NoPrice", "line": 14.5, "over_odds": None}]


@pytest.mark.parametrize("payload", [
    {}, {"bookmakers": []}, {"bookmakers": [{"key": "fanduel"}]},
    {"bookmakers": [{"key": "other", "markets": []}]},
    {"bookmakers": [{"key": "fanduel", "markets": [{"key": "h2h", "outcomes": []}]}]},
])
def test_alt_parser_handles_missing_pieces(payload):
    assert nba_props.parse_alt_lines(payload) == []


def test_player_parser_skips_malformed_outcomes():
    payload = player_payload("player_points", [
        {"name": "Over", "description": "A", "price": -120, "point": 20.5},
        {"name": "Push", "description": "A", "price": -120, "point": 20.5},
        {"name": "Over", "price": -120, "point": 20.5},
        {"name": "Over", "description": "B", "price": -120},
        {"name": "Under", "description": "A", "price": 100, "point": 20.5}])
    assert nba_props.parse_player_lines(payload) == [
        {"player": "A", "line": 20.5, "over_odds": -120, "under_odds": 100}]


def test_one_player_with_two_lines_gives_two_rows():
    payload = player_payload("player_points", [
        {"name": "Over", "description": "A", "price": -110, "point": 20.5},
        {"name": "Over", "description": "A", "price": 150, "point": 24.5}])
    rows = nba_props.parse_player_lines(payload)
    assert sorted(r["line"] for r in rows) == [20.5, 24.5]


def test_player_parser_can_read_another_market():
    payload = player_payload("player_rebounds", [
        {"name": "Over", "description": "A", "price": -110, "point": 8.5}])
    assert nba_props.parse_player_lines(payload) == []
    assert nba_props.parse_player_lines(payload, market="player_rebounds")[0]["line"] == 8.5


def test_the_book_with_no_markets_key_is_handled():
    assert nba_props.parse_player_lines({"bookmakers": [{"key": "fanduel"}]}) == []


# ---- the archive -------------------------------------------------------------------------------------------------------

LINES = [{"player": "A", "line": 20.5, "over_odds": -110, "under_odds": -110},
         {"player": "B", "line": 8.5, "over_odds": 120, "under_odds": -150}]


def test_append_writes_one_header_and_one_row_per_line(tmp_path):
    path = tmp_path / "sub" / "props.csv"
    nba_props.append_snapshot(EVENT, "early", LINES, "2026-11-04T20:00:00+00:00", path)
    nba_props.append_snapshot(EVENT, "late", LINES[:1], "2026-11-04T23:00:00+00:00", path)
    text = path.read_text(encoding="utf-8").splitlines()
    assert text[0].split(",") == nba_props.COLUMNS
    assert len(text) == 1 + 3
    assert sum(1 for line_ in text if line_.startswith("fetched_at")) == 1


def test_snapshots_round_trip(tmp_path):
    path = tmp_path / "props.csv"
    nba_props.append_snapshot(EVENT, "early", LINES, "2026-11-04T20:00:00+00:00", path)
    loaded = nba_props.load_snapshots(path)
    assert list(loaded["player"]) == ["A", "B"] and list(loaded["phase"]) == ["early"] * 2
    assert loaded.loc[1, "over_odds"] == 120 and loaded.loc[0, "line"] == 20.5


def test_a_missing_archive_loads_empty(tmp_path):
    loaded = nba_props.load_snapshots(tmp_path / "none.csv")
    assert loaded.empty and list(loaded.columns) == nba_props.COLUMNS


def test_a_missing_price_is_stored_blank_not_as_text_none(tmp_path):
    path = tmp_path / "props.csv"
    nba_props.append_snapshot(EVENT, "early",
                              [{"player": "A", "line": 20.5, "over_odds": -110, "under_odds": None}],
                              "t", path)
    assert pd.isna(nba_props.load_snapshots(path).loc[0, "under_odds"])


# ---- re-pricing archived snapshots ---------------------------------------------------------------------------------------

def archive(tmp_path, *snapshots):
    path = tmp_path / "props.csv"
    for event, phase, lines, stamp in snapshots:
        nba_props.append_snapshot(event, phase, lines, stamp, path)
    return nba_props.load_snapshots(path)


def test_only_early_snapshots_are_regrouped(tmp_path):
    snaps = archive(tmp_path, (EVENT, "early", LINES, "t1"), (EVENT, "late", LINES, "t2"))
    grouped = nba_props.early_snapshots_by_event(snaps)
    assert len(grouped) == 1
    event, lines = grouped[0]
    assert event == EVENT and len(lines) == 2


def test_a_repeated_line_keeps_the_latest_price(tmp_path):
    newer = [{"player": "A", "line": 20.5, "over_odds": -125, "under_odds": 105}]
    snaps = archive(tmp_path, (EVENT, "early", LINES, "t1"), (EVENT, "early", newer, "t2"))
    _, lines = nba_props.early_snapshots_by_event(snaps)[0]
    a = next(row for row in lines if row["player"] == "A")
    assert (a["over_odds"], a["under_odds"]) == (-125, 105)
    assert len(lines) == 2


def test_prices_come_back_as_ints_and_missing_ones_as_none(tmp_path):
    lines = [{"player": "A", "line": 20.5, "over_odds": -110, "under_odds": None}]
    snaps = archive(tmp_path, (EVENT, "early", lines, "t1"))
    _, regrouped = nba_props.early_snapshots_by_event(snaps)[0]
    assert regrouped[0]["over_odds"] == -110 and isinstance(regrouped[0]["over_odds"], int)
    assert regrouped[0]["under_odds"] is None
    assert isinstance(regrouped[0]["line"], float)


def test_two_games_stay_separate(tmp_path):
    other = EVENT | {"event_id": "e2", "home": "Boston Celtics"}
    snaps = archive(tmp_path, (EVENT, "early", LINES, "t1"), (other, "early", LINES[:1], "t1"))
    grouped = nba_props.early_snapshots_by_event(snaps)
    assert sorted(e["event_id"] for e, _ in grouped) == ["e1", "e2"]


def test_no_early_snapshots_gives_nothing(tmp_path):
    snaps = archive(tmp_path, (EVENT, "late", LINES, "t1"))
    assert nba_props.early_snapshots_by_event(snaps) == []


@pytest.mark.parametrize("value, expected", [
    (-110.0, -110), (120, 120), (-105.5, -105.5), (float("nan"), None), (None, None)])
def test_odds_normaliser(value, expected):
    assert nba_props._odds(value) == expected
