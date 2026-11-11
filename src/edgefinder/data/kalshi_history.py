"""Kalshi's archive of settled markets, for testing the models on a whole past season.

Kalshi keeps every settled market and its hourly price history, free and without a key
(`/historical/markets` and `/historical/markets/{ticker}/candlesticks`). For a backtest each
market needs three things, all decided here so the rules are tested in one place:

- **when the game tipped off.** Kalshi's player markets carry an `occurrence_datetime` (or, on
  older ones, an `expected_expiration_time`) three hours after the scheduled tip; the backtest
  prefers NBA's official schedule and drops any game where the two disagree;
- **the price before tip-off.** The last hourly candle that closed at least 15 minutes before
  tip, never one that includes game time;
- **a clean result.** Yes or no. A player who never took the court settles at a price instead,
  and that market is left out.
"""

import datetime as dt
import math
from collections.abc import Callable

from . import kalshi

HISTORY = "/historical/markets"
TIP_BEFORE_OCCURRENCE = dt.timedelta(hours=3)
SAFETY_MARGIN = dt.timedelta(minutes=15)
PAGE_LIMIT = 1000
MAX_PAGES = 200
FEE_RATE = 0.07              # Kalshi's taker fee: 7% of price x (1 - price), per contract

Getter = Callable[[str, dict], dict]


def _moment(text) -> dt.datetime | None:
    if not isinstance(text, str):
        return None
    try:
        moment = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def tip_time(market: dict) -> dt.datetime | None:
    """Scheduled tip-off: three hours before the market's occurrence time, or before its expected
    expiration on older markets that have no occurrence time (the two are equal on 99% of the
    markets that have both, and match NBA's official schedule on 99% of 2025-26)."""
    occurrence = (_moment(market.get("occurrence_datetime"))
                  or _moment(market.get("expected_expiration_time")))
    return None if occurrence is None else occurrence - TIP_BEFORE_OCCURRENCE


def outcome(market: dict) -> int | None:
    """1 for yes, 0 for no; None for anything else (a price settlement, a void)."""
    try:
        value = float(market.get("settlement_value_dollars"))
    except (TypeError, ValueError):
        return None
    if market.get("result") == "yes" and value == 1.0:
        return 1
    if market.get("result") == "no" and value == 0.0:
        return 0
    return None


def _close(candle: dict, side: str) -> float | None:
    block = candle.get(side)
    value = block.get("close") if isinstance(block, dict) else None
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def pre_tip_quote(candles: list[dict], tip: dt.datetime,
                  margin: dt.timedelta = SAFETY_MARGIN) -> dict | None:
    """The yes bid and ask in the last hourly candle that closed at least `margin` before tip,
    and the volume traded up to then. None when there is no such candle or no real two-sided
    book in it (a bid of 0, an ask of 1, or a bid above the ask)."""
    cutoff = (tip - margin).timestamp()
    before = sorted((c for c in candles if c.get("end_period_ts", math.inf) <= cutoff),
                    key=lambda c: c["end_period_ts"])
    if not before:
        return None
    last = before[-1]
    bid, ask = _close(last, "yes_bid"), _close(last, "yes_ask")
    if bid is None or ask is None or bid <= 0.0 or ask >= 1.0 or bid > ask:
        return None
    volume = sum(float(c.get("volume") or 0) for c in before)
    return {"yes_bid": bid, "yes_ask": ask, "volume": volume,
            "quoted_at": dt.datetime.fromtimestamp(last["end_period_ts"], dt.timezone.utc)
            .isoformat()}


def settled_rows(markets: list[dict]) -> list[dict]:
    """One row per recognised player market with a clean result and a known tip-off."""
    rows = []
    for market in markets:
        parsed = kalshi.parse_markets({"markets": [market]})
        hit, tip = outcome(market), tip_time(market)
        if not parsed or hit is None or tip is None:
            continue
        row = parsed[0]
        rows.append({"ticker": row["ticker"], "stat": row["stat"], "player": row["player"],
                     "away": row["away"], "home": row["home"], "game_date": row["game_date"],
                     "threshold": row["threshold"], "hit": hit, "tip": tip.isoformat(),
                     "total_volume": row["volume"]})
    return rows


def fetch_markets(series: str, get: Getter) -> list[dict]:
    """Every settled market in a series, following the cursor. `get(path, params)` returns the
    decoded JSON (injected, so tests and the backtest's cache decide how requests are made)."""
    markets, cursor = [], None
    for _ in range(MAX_PAGES):
        params = {"series_ticker": series, "limit": PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        page = get(HISTORY, params)
        markets += page.get("markets") or []
        cursor = page.get("cursor")
        if not cursor:
            return markets
    raise kalshi.KalshiDataError(f"more than {MAX_PAGES} pages of {series}; stopping")


def candles_path(ticker: str) -> str:
    return f"{HISTORY}/{ticker}/candlesticks"


def taker_fee(price: float) -> float:
    """Kalshi's fee per $1 contract bought at `price` (before rounding up to the cent on the
    order). Largest at 50 cents, small near 0 or 1."""
    return FEE_RATE * price * (1.0 - price)
