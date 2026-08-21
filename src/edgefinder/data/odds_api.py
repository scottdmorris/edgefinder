"""Client for The Odds API (the-odds-api.com), FanDuel lines only.

Free tier is 500 requests/month, so responses are cached for
ODDS_CACHE_SECONDS, every response's quota headers are stored for the
sidebar meter, and every fetch is archived to line_history for CLV and
line-movement tracking.

Set the key via the ODDS_API_KEY environment variable or a
data/odds_api_key.txt file (git-ignored).
"""

import os
from pathlib import Path

import requests

from . import cache, line_history

BASE = "https://api.the-odds-api.com/v4"
ODDS_CACHE_SECONDS = 15 * 60
REQUEST_TIMEOUT = 20
SPORT_KEYS = {"mlb": "baseball_mlb", "nba": "basketball_nba"}
SOCCER_LEAGUES = {
    "EPL": "soccer_epl",
    "La Liga": "soccer_spain_la_liga",
    "Bundesliga": "soccer_germany_bundesliga",
    "Serie A": "soccer_italy_serie_a",
    "Ligue 1": "soccer_france_ligue_one",
}
UFC_SPORT_KEY = "mma_mixed_martial_arts"
KEY_FILE = Path(__file__).resolve().parents[3] / "data" / "odds_api_key.txt"
QUOTA_CACHE_KEY = "odds_api_quota"


class OddsApiError(Exception):
    pass


def get_api_key() -> str | None:
    env_key = os.environ.get("ODDS_API_KEY", "").strip()
    if env_key:
        return env_key
    if KEY_FILE.exists():
        file_key = KEY_FILE.read_text(encoding="utf-8").strip()
        if file_key:
            return file_key
    return None


def get_quota() -> dict | None:
    """Most recent quota headers: {'remaining': str, 'used': str}."""
    return cache.get(QUOTA_CACHE_KEY, float("inf"))


def fanduel_odds(sport: str) -> list[dict]:
    """MLB/NBA moneyline + totals. [] when no API key (manual mode)."""
    sport_key = SPORT_KEYS[sport]
    return _fetch_events(sport_key, "h2h,totals")


def fanduel_soccer(league: str) -> list[dict]:
    """Soccer three-way moneyline (home/draw/away) + totals."""
    return _fetch_events(SOCCER_LEAGUES[league], "h2h,totals")


def fanduel_ufc() -> list[dict]:
    """UFC/MMA moneylines."""
    return _fetch_events(UFC_SPORT_KEY, "h2h")


def _fetch_events(sport_key: str, markets: str) -> list[dict]:
    api_key = get_api_key()
    if not api_key:
        return []
    cache_key = f"odds_{sport_key}_v2"
    cached = cache.get(cache_key, ODDS_CACHE_SECONDS)
    if cached is not None:
        return cached
    url = (
        f"{BASE}/sports/{sport_key}/odds"
        f"?apiKey={api_key}&regions=us&markets={markets}"
        "&bookmakers=fanduel&oddsFormat=american"
    )
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        stale = cache.get(cache_key, float("inf"))
        if stale is not None:
            return stale
        raise OddsApiError(f"Odds API request failed: {exc}") from exc
    _store_quota(response.headers)
    parsed = [_parse_event(event) for event in response.json()]
    parsed = [event for event in parsed if event is not None]
    cache.put(cache_key, parsed)
    line_history.append_snapshots(sport_key, parsed)
    return parsed


def _store_quota(headers) -> None:
    remaining = headers.get("x-requests-remaining")
    used = headers.get("x-requests-used")
    if remaining is not None:
        cache.put(QUOTA_CACHE_KEY, {"remaining": remaining, "used": used})


def _parse_event(event: dict) -> dict | None:
    bookmaker = next(
        (b for b in event.get("bookmakers", []) if b.get("key") == "fanduel"),
        None,
    )
    if bookmaker is None:
        return None
    result = {
        "home": event.get("home_team"),
        "away": event.get("away_team"),
        "commence_time": event.get("commence_time"),
        "home_ml": None,
        "away_ml": None,
        "draw_ml": None,
        "total_line": None,
        "over_odds": None,
        "under_odds": None,
    }
    for market in bookmaker.get("markets", []):
        if market.get("key") == "h2h":
            for outcome in market.get("outcomes", []):
                if outcome.get("name") == result["home"]:
                    result["home_ml"] = outcome.get("price")
                elif outcome.get("name") == result["away"]:
                    result["away_ml"] = outcome.get("price")
                elif outcome.get("name") == "Draw":
                    result["draw_ml"] = outcome.get("price")
        elif market.get("key") == "totals":
            for outcome in market.get("outcomes", []):
                result["total_line"] = outcome.get("point")
                if outcome.get("name") == "Over":
                    result["over_odds"] = outcome.get("price")
                elif outcome.get("name") == "Under":
                    result["under_odds"] = outcome.get("price")
    return result
