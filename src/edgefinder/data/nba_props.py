"""FanDuel NBA player-prop lines from The Odds API, archived for CLV.

Checked against the live API: a props call costs 1 request per game per
market (the same call returns every listed player), and the events list
is free. That is why snapshots are budgeted by game, not by player.

Error messages never include the request URL, because it carries the
API key.
"""

import csv
from pathlib import Path

import pandas as pd
import requests

from . import cache, odds_api

PROPS_PATH = Path(__file__).resolve().parents[3] / "data" / "nba_prop_lines.csv"
SPORT_KEY = "basketball_nba"
BOOKMAKER = "fanduel"
MARKET = "player_points"
QUOTA_RESERVE = 100  # never spend the last requests; the board needs them

COLUMNS = [
    "fetched_at", "phase", "event_id", "commence_time", "home", "away",
    "player", "line", "over_odds", "under_odds",
]


class PropsApiError(Exception):
    pass


def _get(path: str, params: dict) -> requests.Response:
    api_key = odds_api.get_api_key()
    if not api_key:
        raise PropsApiError("No Odds API key configured")
    try:
        response = requests.get(
            f"{odds_api.BASE}{path}",
            params={"apiKey": api_key, **params},
            timeout=odds_api.REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PropsApiError(f"Odds API request failed ({type(exc).__name__})") from None
    if not response.ok:
        raise PropsApiError(f"Odds API returned HTTP {response.status_code}")
    _store_quota(response.headers)
    return response


def _store_quota(headers) -> None:
    remaining = headers.get("x-requests-remaining")
    if remaining is not None:
        cache.put(odds_api.QUOTA_CACHE_KEY,
                  {"remaining": remaining, "used": headers.get("x-requests-used")})


def requests_remaining() -> int | None:
    quota = odds_api.get_quota()
    try:
        return int(quota["remaining"]) if quota else None
    except (KeyError, ValueError):
        return None


def upcoming_events() -> list[dict]:
    """Upcoming and live NBA games. Free: costs no requests."""
    events = _get(f"/sports/{SPORT_KEY}/events", {}).json()
    return [
        {"event_id": e["id"], "commence_time": e["commence_time"],
         "home": e["home_team"], "away": e["away_team"]}
        for e in events
    ]


def fetch_event_lines(event: dict) -> list[dict]:
    """One game's player-point lines. Costs 1 request."""
    payload = _get(
        f"/sports/{SPORT_KEY}/events/{event['event_id']}/odds",
        {"regions": "us", "markets": MARKET, "bookmakers": BOOKMAKER,
         "oddsFormat": "american"},
    ).json()
    return parse_player_lines(payload)


def parse_player_lines(payload: dict, market: str = MARKET) -> list[dict]:
    """Pair each player's Over/Under outcomes into one row per line."""
    book = next((b for b in payload.get("bookmakers", []) if b.get("key") == BOOKMAKER), None)
    if book is None:
        return []
    market_data = next((m for m in book.get("markets", []) if m.get("key") == market), None)
    if market_data is None:
        return []
    rows: dict[tuple, dict] = {}
    for outcome in market_data.get("outcomes", []):
        player, point, side = outcome.get("description"), outcome.get("point"), outcome.get("name")
        if player is None or point is None or side not in ("Over", "Under"):
            continue
        row = rows.setdefault(
            (player, point),
            {"player": player, "line": point, "over_odds": None, "under_odds": None},
        )
        row["over_odds" if side == "Over" else "under_odds"] = outcome.get("price")
    return list(rows.values())


def append_snapshot(event: dict, phase: str, lines: list[dict],
                    fetched_at: str, path: Path | None = None) -> None:
    path = path or PROPS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        for line in lines:
            writer.writerow({
                "fetched_at": fetched_at, "phase": phase,
                "event_id": event["event_id"], "commence_time": event["commence_time"],
                "home": event["home"], "away": event["away"],
                "player": line["player"], "line": line["line"],
                "over_odds": line["over_odds"], "under_odds": line["under_odds"],
            })


def load_snapshots(path: Path | None = None) -> pd.DataFrame:
    path = path or PROPS_PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path)


def _odds(value) -> int | float | None:
    if pd.isna(value):
        return None
    return int(value) if float(value).is_integer() else float(value)


def early_snapshots_by_event(snapshots: pd.DataFrame) -> list[tuple[dict, list[dict]]]:
    """Regroup archived early snapshots into (event, lines) pairs, in the
    shape the fetcher produces, so they can be priced again by another
    model. Late snapshots are ignored."""
    early = snapshots[snapshots["phase"] == "early"]
    grouped = []
    for event_id, group in early.groupby("event_id", sort=False):
        group = group.drop_duplicates(["player", "line"], keep="last")
        first = group.iloc[0]
        event = {"event_id": event_id, "commence_time": first["commence_time"],
                 "home": first["home"], "away": first["away"]}
        lines = [
            {"player": row.player, "line": float(row.line),
             "over_odds": _odds(row.over_odds), "under_odds": _odds(row.under_odds)}
            for row in group.itertuples()
        ]
        grouped.append((event, lines))
    return grouped
