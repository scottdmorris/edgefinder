"""Kalshi NBA player-prop markets, from Kalshi's public market-data API.

No account or key is needed. Checked against the live API: every market is
a yes/no "N+" threshold contract (e.g. "Kevin Durant: 35+ points"), prices
are strings in dollars, and an empty book shows up as a bid of 0.0000 or an
ask of 1.0000 rather than as a missing field.

PRICES ARE BEFORE KALSHI'S TRADING FEES. A contract that costs $0.40 pays
$1.00 if it wins, but Kalshi charges a fee on top that depends on the price
and the number of contracts (see Kalshi's fee schedule). Every price,
American-odds figure and probability from this module therefore flatters the
bettor slightly; do not compare them to a sportsbook's all-in price without
allowing for that. Spreads are also often wide and books thin, so a quoted
ask is not necessarily a price you can trade size at.

Error messages never include the request URL or response body.
"""

import math
import re
from datetime import date

import requests

from ..betting import odds_math

BASE = "https://api.elections.kalshi.com/trade-api/v2"
REQUEST_TIMEOUT = 20
PAGE_LIMIT = 200
MAX_PAGES = 20  # a safety stop; one series is a few hundred markets at most
BOOK = "kalshi"

# Kalshi series ticker -> the stat key used by models.nba_stat_model.STATS.
# KXNBAGAME (game winners) is deliberately absent.
SERIES_STATS = {
    "KXNBAPTS": "points",
    "KXNBAREB": "rebounds",
    "KXNBAAST": "assists",
    "KXNBA3PT": "threes",
}

# is_liquid: a contract is "liquid" when both sides of the yes book are
# quoted, the yes bid/ask spread is at most MAX_LIQUID_SPREAD dollars, and at
# least MIN_LIQUID_VOLUME contracts have traded. These are judgement calls,
# not Kalshi's: they exist to flag the empty and one-sided books that make an
# ask meaningless, not to certify a price as fair.
MAX_LIQUID_SPREAD = 0.10
MIN_LIQUID_VOLUME = 25.0

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}

# KXNBAPTS-26NOV04MINHOU-HOUKDURANT7-35: series, date, away+home, player, N
_TICKER = re.compile(
    r"^(?P<series>[A-Z0-9]+)-(?P<yy>\d{2})(?P<mon>[A-Z]{3})(?P<dd>\d{2})"
    r"(?P<away>[A-Z]{3})(?P<home>[A-Z]{3})-[A-Z]{3}[A-Z0-9.'_]+-(?P<n>\d{1,3})$"
)
# "Kevin Durant: 35+" or "Kevin Durant: 35+ points"
_LABEL = re.compile(r"^(?P<name>.+?):\s*(?P<n>\d{1,3})\+")


class KalshiDataError(Exception):
    pass


# ---- price helpers -------------------------------------------------------

def _check_price(dollars: float) -> float:
    """A tradable contract price is strictly between $0 and $1."""
    price = float(dollars)
    if not math.isfinite(price) or not 0.0 < price < 1.0:
        raise ValueError("contract price must be above 0 and below 1 dollar")
    return price


def implied_probability(dollars: float) -> float:
    """The probability a contract price implies: $0.35 is 35%.

    Before Kalshi's trading fees, so a buyer's true break-even is a little
    higher than this."""
    return _check_price(dollars)


def dollars_to_american(dollars: float) -> int:
    """American odds for buying a $1-payout contract at this price.

    $0.50 is +100, $0.01 is +9900, $0.99 is -9900. Before Kalshi's trading
    fees, so the real payout is slightly worse than the odds returned here.
    Raises ValueError for prices at or outside $0 and $1, which have no odds."""
    return round(odds_math.prob_to_american(_check_price(dollars)))


# ---- parsing -------------------------------------------------------------

def _price(value) -> float | None:
    """A quoted price in dollars, or None for a missing, malformed or empty
    quote (0.0000 bid / 1.0000 ask is how Kalshi shows a side with nobody)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or not 0.0 < price < 1.0:
        return None
    return price


def _volume(value) -> float:
    try:
        volume = float(value)
    except (TypeError, ValueError):
        return 0.0
    return volume if math.isfinite(volume) and volume > 0 else 0.0


def _game_date(yy: str, mon: str, dd: str) -> date | None:
    month = _MONTHS.get(mon)
    if month is None:
        return None
    try:
        return date(2000 + int(yy), month, int(dd))
    except ValueError:
        return None


def _player_name(market: dict, threshold: int) -> str | None:
    for field in ("yes_sub_title", "title"):
        text = market.get(field)
        match = _LABEL.match(text) if isinstance(text, str) else None
        if match and int(match["n"]) == threshold:
            return match["name"].strip()
    return None


def _parse_market(market) -> dict | None:
    if not isinstance(market, dict):
        return None
    ticker = market.get("ticker")
    match = _TICKER.match(ticker) if isinstance(ticker, str) else None
    if match is None or match["series"] not in SERIES_STATS:
        return None
    game_date = _game_date(match["yy"], match["mon"], match["dd"])
    threshold = int(match["n"])
    player = _player_name(market, threshold)
    if game_date is None or player is None or threshold < 1:
        return None
    yes_bid, yes_ask = _price(market.get("yes_bid_dollars")), _price(market.get("yes_ask_dollars"))
    no_bid, no_ask = _price(market.get("no_bid_dollars")), _price(market.get("no_ask_dollars"))
    spread = None if yes_bid is None or yes_ask is None else round(yes_ask - yes_bid, 4)
    volume = _volume(market.get("volume_fp"))
    return {
        "stat": SERIES_STATS[match["series"]],
        "player": player,
        "away": match["away"],
        "home": match["home"],
        "game_date": game_date.isoformat(),
        "threshold": threshold,
        "yes_ask": yes_ask,
        "no_ask": no_ask,
        "yes_bid": yes_bid,
        "no_bid": no_bid,
        "spread": spread,
        "volume": volume,
        "is_liquid": (spread is not None and spread >= 0
                      and spread <= MAX_LIQUID_SPREAD and volume >= MIN_LIQUID_VOLUME),
        "ticker": ticker,
    }


def parse_markets(payload) -> list[dict]:
    """One row per recognised NBA player-threshold market in a /markets
    response. Anything unrecognised (game winners, other series, odd tickers,
    labels that disagree with the ticker) is skipped. A price that is missing,
    malformed or an empty side of the book is None, never a guess.

    Prices are dollars before Kalshi's trading fees. game_date is the date in
    the ticker (an ISO string); close_time is settlement, not tip-off, so
    tip-off time is not available here."""
    markets = payload.get("markets") if isinstance(payload, dict) else None
    if not isinstance(markets, list):
        return []
    rows = (_parse_market(m) for m in markets)
    return [row for row in rows if row is not None]


def to_lines(rows: list[dict]) -> list[dict]:
    """Rows as prop lines, in the shape nba_props.parse_player_lines makes
    (player, line, over_odds, under_odds) plus stat and book.

    "N+" is an over at N - 0.5, priced at the yes ask; the no side is the
    under, priced at the no ask. A row missing either ask is skipped. Odds
    are American and BEFORE Kalshi's trading fees."""
    lines = []
    for row in rows:
        yes_ask, no_ask = row.get("yes_ask"), row.get("no_ask")
        if yes_ask is None or no_ask is None:
            continue
        try:
            over, under = dollars_to_american(yes_ask), dollars_to_american(no_ask)
        except (TypeError, ValueError):
            continue
        lines.append({
            "player": row["player"],
            "line": row["threshold"] - 0.5,
            "over_odds": over,
            "under_odds": under,
            "stat": row["stat"],
            "book": BOOK,
        })
    return lines


# ---- fetching ------------------------------------------------------------

def _get_page(series: str, cursor: str | None) -> dict:
    params = {"series_ticker": series, "status": "open", "limit": PAGE_LIMIT}
    if cursor:
        params["cursor"] = cursor
    try:
        response = requests.get(f"{BASE}/markets", params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise KalshiDataError(f"Kalshi request failed ({type(exc).__name__})") from None
    if not response.ok:
        raise KalshiDataError(f"Kalshi returned HTTP {response.status_code}")
    try:
        page = response.json()
    except ValueError:
        raise KalshiDataError("Kalshi returned an unreadable response") from None
    if not isinstance(page, dict) or not isinstance(page.get("markets"), list):
        raise KalshiDataError("Kalshi returned an unexpected response")
    return page


def fetch_series(series: str) -> dict:
    """Every open market in a series (e.g. "KXNBAPTS"), following the
    cursor. Returns {"markets": [...]}, ready for parse_markets. Any failure
    raises KalshiDataError, with no URL or response details in the message."""
    if series not in SERIES_STATS:
        raise KalshiDataError("Unsupported Kalshi series")
    markets: list = []
    cursor = None
    for _ in range(MAX_PAGES):
        page = _get_page(series, cursor)
        markets.extend(page["markets"])
        next_cursor = page.get("cursor")
        if not next_cursor or not isinstance(next_cursor, str) or next_cursor == cursor:
            return {"markets": markets}
        cursor = next_cursor
    raise KalshiDataError("Kalshi returned too many pages")
