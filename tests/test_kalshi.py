import pytest
import requests

from edgefinder.data import kalshi


def market(ticker, label, yes_bid="0.0500", yes_ask="0.3300", no_bid="0.6700",
           no_ask="0.9500", volume="473.27", **extra):
    stat_word = {"KXNBAPTS": "points", "KXNBAREB": "rebounds",
                 "KXNBAAST": "assists", "KXNBA3PT": "threes"}.get(ticker.split("-")[0], "wins")
    return {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", 2)[0],
        "title": f"{label} {stat_word}",
        "yes_sub_title": label,
        "no_sub_title": label,
        "status": "active",
        "yes_bid_dollars": yes_bid, "yes_ask_dollars": yes_ask,
        "no_bid_dollars": no_bid, "no_ask_dollars": no_ask,
        "last_price_dollars": "0.2000",
        "volume_fp": volume, "volume_24h_fp": "10.00", "open_interest_fp": "196.00",
        "close_time": "2026-11-07T03:30:00Z",
        **extra,
    }


DURANT_35 = market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-35", "Kevin Durant: 35+")
PAYLOAD = {
    "cursor": "",
    "markets": [
        DURANT_35,
        market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-25", "Kevin Durant: 25+",
               yes_bid="0.5400", yes_ask="0.5800", no_bid="0.4200", no_ask="0.4600"),
        market("KXNBAREB-26NOV04MINHOU-MINRGOBERT27-12", "Rudy Gobert: 12+",
               yes_bid="0.2000", yes_ask="0.2400", no_bid="0.7600", no_ask="0.8000"),
        market("KXNBAAST-26NOV04MINHOU-HOUAS28-8", "Amen Thompson: 8+"),
        market("KXNBA3PT-26NOV04MINHOU-MINAEDWARDS5-4", "Anthony Edwards: 4+"),
        market("KXNBAGAME-26NOV04MINHOU-HOU", "Houston wins"),
    ],
}


def by_ticker(rows):
    return {row["ticker"]: row for row in rows}


# ---- price helpers -------------------------------------------------------

@pytest.mark.parametrize("dollars,american", [
    (0.01, 9900), (0.50, 100), (0.99, -9900), (0.25, 300), (0.75, -300),
    ("0.4000", 150),
])
def test_dollars_to_american(dollars, american):
    assert kalshi.dollars_to_american(dollars) == american


@pytest.mark.parametrize("bad", [0, 0.0, 1, 1.0, -0.2, 1.5, float("nan"), float("inf")])
def test_prices_outside_the_open_interval_have_no_odds(bad):
    with pytest.raises(ValueError):
        kalshi.dollars_to_american(bad)
    with pytest.raises(ValueError):
        kalshi.implied_probability(bad)


def test_implied_probability_is_the_price():
    assert kalshi.implied_probability(0.35) == pytest.approx(0.35)
    assert kalshi.implied_probability("0.0100") == pytest.approx(0.01)


def test_docstrings_state_that_prices_exclude_fees():
    for obj in (kalshi, kalshi.dollars_to_american, kalshi.implied_probability,
                kalshi.parse_markets, kalshi.to_lines):
        assert "fee" in obj.__doc__.lower()


# ---- parse_markets -------------------------------------------------------

def test_a_market_becomes_one_row():
    row = by_ticker(kalshi.parse_markets(PAYLOAD))[DURANT_35["ticker"]]
    assert row == {
        "stat": "points", "player": "Kevin Durant",
        "away": "MIN", "home": "HOU", "game_date": "2026-11-04", "threshold": 35,
        "yes_ask": 0.33, "no_ask": 0.95, "yes_bid": 0.05, "no_bid": 0.67,
        "spread": 0.28, "volume": 473.27, "is_liquid": False,
        "ticker": DURANT_35["ticker"],
    }


def test_every_series_maps_to_a_model_stat():
    from edgefinder.models import nba_stat_model
    assert set(kalshi.SERIES_STATS.values()) <= set(nba_stat_model.STATS)
    stats = {r["stat"] for r in kalshi.parse_markets(PAYLOAD)}
    assert stats == {"points", "rebounds", "assists", "threes"}


def test_game_winner_markets_are_ignored():
    rows = kalshi.parse_markets(PAYLOAD)
    assert len(rows) == 5
    assert not any("GAME" in r["ticker"] for r in rows)


def test_a_tight_traded_book_is_liquid_and_a_wide_or_quiet_one_is_not():
    rows = by_ticker(kalshi.parse_markets(PAYLOAD))
    assert rows["KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-25"]["is_liquid"] is True
    assert rows[DURANT_35["ticker"]]["is_liquid"] is False  # 0.28 wide
    quiet = market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-20", "Kevin Durant: 20+",
                   yes_bid="0.5400", yes_ask="0.5800", volume="3.00")
    assert kalshi.parse_markets({"markets": [quiet]})[0]["is_liquid"] is False


def test_an_empty_side_of_the_book_is_none_and_not_liquid():
    empty = market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-45", "Kevin Durant: 45+",
                   yes_bid="0.0000", yes_ask="1.0000", no_bid="0.0000", no_ask="1.0000",
                   volume="500.00")
    row = kalshi.parse_markets({"markets": [empty]})[0]
    assert row["yes_bid"] is None and row["yes_ask"] is None
    assert row["no_bid"] is None and row["no_ask"] is None
    assert row["spread"] is None
    assert row["is_liquid"] is False


@pytest.mark.parametrize("value", [None, "", "abc", "nan", "-0.1", "1.5", [], True])
def test_malformed_prices_become_none(value):
    bad = market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-35", "Kevin Durant: 35+",
                 yes_ask=value, no_ask=value)
    row = kalshi.parse_markets({"markets": [bad]})[0]
    assert row["yes_ask"] is None and row["no_ask"] is None
    assert row["spread"] is not None or row["yes_bid"] is not None


def test_missing_price_fields_and_volume_do_not_break_parsing():
    bare = {"ticker": "KXNBAREB-26NOV04MINHOU-HOUAS28-10",
            "yes_sub_title": "Alperen Sengun: 10+"}
    row = kalshi.parse_markets({"markets": [bare]})[0]
    assert row["player"] == "Alperen Sengun"
    assert row["yes_ask"] is None and row["spread"] is None
    assert row["volume"] == 0.0 and row["is_liquid"] is False


def test_player_name_falls_back_to_the_title():
    m = market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-35", "Kevin Durant: 35+")
    del m["yes_sub_title"]
    assert kalshi.parse_markets({"markets": [m]})[0]["player"] == "Kevin Durant"


@pytest.mark.parametrize("ticker", [
    "", "garbage", "KXNBAPTS", "KXNBAPTS-26NOV04MINHOU-HOUKDURANT7",
    "KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-x", "KXNBAPTS-26NOV04MIN-HOUKDURANT7-35",
    "KXNBAPTS-26XYZ04MINHOU-HOUKDURANT7-35",   # not a month
    "KXNBAPTS-26NOV31MINHOU-HOUKDURANT7-35",   # not a date (November has 30 days)
    "KXMLBHIT-26NOV04MINHOU-HOUKDURANT7-35",   # another series
    "KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-0",    # zero threshold
    None, 5,
])
def test_unrecognised_tickers_are_skipped(ticker):
    m = market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-35", "Kevin Durant: 35+")
    m["ticker"] = ticker
    assert kalshi.parse_markets({"markets": [m]}) == []


def test_a_label_that_disagrees_with_the_ticker_is_skipped():
    m = market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-35", "Kevin Durant: 30+")
    m["title"] = "Kevin Durant: 30+ points"
    assert kalshi.parse_markets({"markets": [m]}) == []


@pytest.mark.parametrize("payload", [None, [], "x", {}, {"markets": None},
                                     {"markets": "no"}, {"markets": [None, 3, "x", {}]}])
def test_junk_payloads_give_no_rows(payload):
    assert kalshi.parse_markets(payload) == []


# ---- to_lines ------------------------------------------------------------

def test_lines_have_the_props_shape_plus_stat_and_book():
    rows = kalshi.parse_markets({"markets": [
        market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-25", "Kevin Durant: 25+",
               yes_bid="0.5400", yes_ask="0.5800", no_bid="0.4200", no_ask="0.4600")]})
    assert kalshi.to_lines(rows) == [{
        "player": "Kevin Durant", "line": 24.5,
        "over_odds": -138, "under_odds": 117,
        "stat": "points", "book": "kalshi",
    }]


def test_to_lines_matches_the_keys_parse_player_lines_makes():
    from edgefinder.data import nba_props
    payload = {"bookmakers": [{"key": "fanduel", "markets": [{"key": "player_points", "outcomes": [
        {"name": "Over", "description": "A", "price": -110, "point": 1.5}]}]}]}
    expected = set(nba_props.parse_player_lines(payload)[0])
    line = kalshi.to_lines(kalshi.parse_markets(PAYLOAD))[0]
    assert expected <= set(line) and set(line) - expected == {"stat", "book"}


def test_rows_missing_either_ask_are_skipped():
    rows = kalshi.parse_markets({"markets": [
        market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-35", "Kevin Durant: 35+", yes_ask="1.0000"),
        market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-30", "Kevin Durant: 30+", no_ask=None),
        market("KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-25", "Kevin Durant: 25+"),
    ]})
    lines = kalshi.to_lines(rows)
    assert [l["line"] for l in lines] == [24.5]


def test_to_lines_skips_hand_built_rows_with_unpriceable_asks():
    row = {"player": "A", "threshold": 10, "stat": "points", "yes_ask": 0.0, "no_ask": 0.5}
    assert kalshi.to_lines([row]) == []


# ---- fetching ------------------------------------------------------------

class FakeResponse:
    def __init__(self, body=None, status=200, bad_json=False):
        self._body, self.status_code, self._bad = body, status, bad_json
        self.ok = status < 400

    def json(self):
        if self._bad:
            raise ValueError("secret-body-details")
        return self._body


def patch_get(monkeypatch, responses):
    calls = []
    queue = list(responses)

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": dict(params), "timeout": timeout})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(kalshi.requests, "get", fake_get)
    return calls


def test_fetch_follows_the_cursor_until_it_is_empty(monkeypatch):
    first = {"markets": [DURANT_35], "cursor": "abc"}
    second = {"markets": [PAYLOAD["markets"][1]], "cursor": "def"}
    third = {"markets": [PAYLOAD["markets"][2]], "cursor": ""}
    calls = patch_get(monkeypatch, [FakeResponse(first), FakeResponse(second), FakeResponse(third)])
    result = kalshi.fetch_series("KXNBAPTS")
    assert len(result["markets"]) == 3
    assert [c["params"].get("cursor") for c in calls] == [None, "abc", "def"]
    assert all(c["params"]["series_ticker"] == "KXNBAPTS" for c in calls)
    assert all(c["params"]["status"] == "open" and c["params"]["limit"] == 200 for c in calls)
    assert all(c["timeout"] == kalshi.REQUEST_TIMEOUT for c in calls)
    assert len(kalshi.parse_markets(result)) == 3


def test_a_missing_cursor_ends_pagination(monkeypatch):
    calls = patch_get(monkeypatch, [FakeResponse({"markets": [DURANT_35]})])
    assert len(kalshi.fetch_series("KXNBAPTS")["markets"]) == 1
    assert len(calls) == 1


def test_a_repeated_cursor_does_not_loop_forever(monkeypatch):
    page = {"markets": [DURANT_35], "cursor": "same"}
    calls = patch_get(monkeypatch, [FakeResponse(page)] * 3)
    assert len(kalshi.fetch_series("KXNBAPTS")["markets"]) == 2
    assert len(calls) == 2


def test_endless_pagination_is_cut_off(monkeypatch):
    pages = [FakeResponse({"markets": [], "cursor": f"c{i}"}) for i in range(kalshi.MAX_PAGES + 1)]
    patch_get(monkeypatch, pages)
    with pytest.raises(kalshi.KalshiDataError):
        kalshi.fetch_series("KXNBAPTS")


def test_unknown_series_never_touches_the_network(monkeypatch):
    calls = patch_get(monkeypatch, [])
    for series in ("KXNBAGAME", "nonsense", ""):
        with pytest.raises(kalshi.KalshiDataError):
            kalshi.fetch_series(series)
    assert calls == []


@pytest.mark.parametrize("failure", [
    requests.ConnectionError("https://api.elections.kalshi.com/secret?key=SECRET"),
    requests.Timeout("https://api.elections.kalshi.com/secret?key=SECRET"),
    FakeResponse(status=500),
    FakeResponse(status=429),
    FakeResponse(bad_json=True),
    FakeResponse(["not", "a", "dict"]),
    FakeResponse({"markets": "nope"}),
    FakeResponse({"cursor": ""}),
])
def test_failed_fetches_raise_one_error_that_leaks_nothing(monkeypatch, failure):
    patch_get(monkeypatch, [failure])
    with pytest.raises(kalshi.KalshiDataError) as caught:
        kalshi.fetch_series("KXNBAPTS")
    message = str(caught.value)
    for leak in ("http", "kalshi.com", "SECRET", "secret", "series_ticker"):
        assert leak not in message


def test_a_failure_on_a_later_page_still_raises(monkeypatch):
    patch_get(monkeypatch, [FakeResponse({"markets": [DURANT_35], "cursor": "abc"}),
                            FakeResponse(status=503)])
    with pytest.raises(kalshi.KalshiDataError):
        kalshi.fetch_series("KXNBAPTS")
