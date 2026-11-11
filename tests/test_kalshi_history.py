import datetime as dt

import pytest

from edgefinder.data import kalshi_history as kh

UTC = dt.timezone.utc


def market(result="no", settlement="0.0000", occurrence="2026-01-11T03:30:00Z",
           ticker="KXNBAPTS-26JAN10NYKSAS-SASVWEMBANYAMA1-25", label="Victor Wembanyama: 25+",
           volume="1200.00"):
    return {"ticker": ticker, "yes_sub_title": label, "title": f"{label} points",
            "result": result, "settlement_value_dollars": settlement,
            "occurrence_datetime": occurrence, "volume_fp": volume, "status": "finalized"}


def candle(end: dt.datetime, bid="0.40", ask="0.42", volume="10"):
    return {"end_period_ts": int(end.timestamp()), "volume": volume,
            "yes_bid": {"close": bid}, "yes_ask": {"close": ask}}


def test_tip_off_is_three_hours_before_kalshi_s_occurrence_time():
    assert kh.tip_time(market()) == dt.datetime(2026, 1, 11, 0, 30, tzinfo=UTC)


def test_older_markets_without_an_occurrence_time_use_the_expected_expiration():
    older = {**market(occurrence=None), "expected_expiration_time": "2026-01-11T02:30:00Z"}
    assert kh.tip_time(older) == dt.datetime(2026, 1, 10, 23, 30, tzinfo=UTC)


def test_a_market_with_neither_time_has_no_tip_off():
    assert kh.tip_time(market(occurrence=None)) is None
    assert kh.tip_time(market(occurrence="soon")) is None


@pytest.mark.parametrize("result, settlement, expected", [
    ("yes", "1.0000", 1), ("no", "0.0000", 0),
    ("yes", "0.4300", None),           # a player who never took the court settles at a price
    ("", "0.0000", None), ("void", "0.0000", None),
])
def test_only_a_clean_yes_or_no_counts_as_a_result(result, settlement, expected):
    assert kh.outcome(market(result, settlement)) == expected


def test_the_quote_is_the_last_hour_that_closed_before_tip_off():
    tip = dt.datetime(2026, 1, 11, 0, 30, tzinfo=UTC)
    candles = [candle(tip - dt.timedelta(hours=2), "0.30", "0.33"),
               candle(tip - dt.timedelta(minutes=30), "0.40", "0.42"),
               candle(tip + dt.timedelta(minutes=30), "0.90", "0.95")]   # in-game: never used
    quote = kh.pre_tip_quote(candles, tip)
    assert (quote["yes_bid"], quote["yes_ask"]) == (0.40, 0.42)
    assert quote["volume"] == 20.0                                       # traded before tip only


def test_an_hour_closing_inside_the_safety_margin_is_not_used():
    tip = dt.datetime(2026, 1, 11, 0, 30, tzinfo=UTC)
    candles = [candle(tip - dt.timedelta(hours=1), "0.30", "0.33"),
               candle(tip - dt.timedelta(minutes=5), "0.40", "0.42")]
    assert kh.pre_tip_quote(candles, tip)["yes_ask"] == 0.33


def test_an_empty_or_crossed_book_gives_no_quote():
    tip = dt.datetime(2026, 1, 11, 0, 30, tzinfo=UTC)
    before = tip - dt.timedelta(hours=1)
    assert kh.pre_tip_quote([], tip) is None
    assert kh.pre_tip_quote([candle(before, None, "0.40")], tip) is None
    assert kh.pre_tip_quote([candle(before, "0.50", "0.40")], tip) is None
    assert kh.pre_tip_quote([candle(before, "0.00", "1.00")], tip) is None    # nobody quoting


def test_settled_rows_keep_parsed_markets_with_a_result_and_a_tip_off():
    rows = kh.settled_rows([market("yes", "1.0000"), market("yes", "0.5000"),
                            {"ticker": "KXNBAGAME-26JAN10NYKSAS-SAS"}])
    assert len(rows) == 1
    row = rows[0]
    assert (row["player"], row["threshold"], row["hit"], row["stat"]) == \
        ("Victor Wembanyama", 25, 1, "points")
    assert row["tip"] == "2026-01-11T00:30:00+00:00"


def test_fetching_every_market_follows_the_cursor():
    pages = {None: {"markets": [market()], "cursor": "c2"},
             "c2": {"markets": [market(), market()], "cursor": ""}}
    seen = []

    def get(path, params):
        seen.append(params.get("cursor"))
        return pages[params.get("cursor")]
    assert len(kh.fetch_markets("KXNBAPTS", get)) == 3
    assert seen == [None, "c2"]


def test_the_taker_fee_is_largest_at_even_money():
    assert kh.taker_fee(0.5) == pytest.approx(0.0175)
    assert kh.taker_fee(0.9) == pytest.approx(0.0063)
    assert kh.taker_fee(0.5) > kh.taker_fee(0.2)
