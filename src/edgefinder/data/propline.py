"""FanDuel and DraftKings player-prop lines from PropLine (prop-line.com), archived as a
second source.

The Odds API's free plan only stretches to FanDuel's points lines. PropLine's free plan
(1,000 requests a day, reset at 00:00 UTC) returns every NBA game's points, rebounds,
assists and threes lines from both books in one request, so the snapshot job makes one
call per run. The lines are kept in their own file; picks, the ledger and the published
record are unchanged.

Checked against the live API on 2026-11-22: its FanDuel points lines matched The Odds
API's exactly on all 14 players of a game pulled at the same moment.

The key is read from PROPLINE_API_KEY or data/propline_key.txt (git-ignored). It travels
in a header, never the URL, and error messages never include it.
"""

import csv
import datetime as dt
import os
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parents[3] / "data"
KEY_PATH = DATA / "propline_key.txt"
LINES_PATH = DATA / "nba_propline_lines.csv"
BASE = "https://api.prop-line.com/v1"
SPORT_KEY = "basketball_nba"
BOOKS = ("fanduel", "draftkings")
MARKETS = {"player_points": "points", "player_rebounds": "rebounds",
           "player_assists": "assists", "player_threes": "threes"}
REQUEST_TIMEOUT = 60
SAME_GAME_HOURS = 6   # PropLine and The Odds API may list a tip time a little differently

COLUMNS = ["fetched_at", "phase", "event_id", "propline_event_id", "commence_time", "home",
           "away", "book", "stat", "player", "player_id", "line", "over_odds", "under_odds",
           "changed_at"]


class PropLineError(Exception):
    pass


def get_api_key() -> str | None:
    env_key = os.environ.get("PROPLINE_API_KEY", "").strip()
    if env_key:
        return env_key
    if KEY_PATH.exists():
        return KEY_PATH.read_text(encoding="utf-8").strip() or None
    return None


def fetch_slate(get=requests.get) -> tuple[list[dict], int | None]:
    """Every listed NBA game with both books' main lines for the four stats. One request.
    Returns the games and the requests left today (None if PropLine did not say)."""
    key = get_api_key()
    if not key:
        raise PropLineError("No PropLine key configured")
    try:
        response = get(f"{BASE}/sports/{SPORT_KEY}/odds", headers={"X-API-Key": key},
                       params={"markets": ",".join(MARKETS), "bookmakers": ",".join(BOOKS)},
                       timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise PropLineError(f"PropLine request failed ({type(exc).__name__})") from None
    if not response.ok:
        raise PropLineError(f"PropLine returned HTTP {response.status_code}")
    remaining = response.headers.get("x-daily-remaining")
    games = response.json()
    if not isinstance(games, list):
        raise PropLineError("PropLine returned an unexpected payload")
    return games, int(remaining) if remaining and remaining.isdigit() else None


def parse_lines(game: dict) -> list[dict]:
    """One row per book, stat, player and line, pairing Over with Under. Main lines only:
    the "X+" milestone ladders and books outside BOOKS are skipped."""
    rows: dict[tuple, dict] = {}
    for listing in game.get("bookmakers", []):
        book = listing.get("key")
        if book not in BOOKS:
            continue
        for market in listing.get("markets", []):
            stat = MARKETS.get(market.get("key"))
            if stat is None or market.get("line_type") != "main":
                continue
            for outcome in market.get("outcomes", []):
                player, point, side = (outcome.get("description"), outcome.get("point"),
                                       outcome.get("name"))
                if player is None or point is None or side not in ("Over", "Under"):
                    continue
                row = rows.setdefault((book, stat, player, point), {
                    "book": book, "stat": stat, "player": player,
                    "player_id": outcome.get("player_id"), "line": point,
                    "over_odds": None, "under_odds": None, "changed_at": None})
                row["over_odds" if side == "Over" else "under_odds"] = outcome.get("price")
                row["changed_at"] = max(filter(None, (row["changed_at"],
                                                      outcome.get("last_change_at"))), default=None)
    return list(rows.values())


def _when(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def match_game(event: dict, games: list[dict]) -> dict | None:
    """PropLine's listing of one of our (Odds API) games: same teams, tip within hours."""
    tip = _when(event["commence_time"])
    for game in games:
        if (game.get("home_team") == event["home"] and game.get("away_team") == event["away"]
                and abs(_when(game["commence_time"]) - tip) <= dt.timedelta(hours=SAME_GAME_HOURS)):
            return game
    return None


def archive(games: list[dict], due: list[tuple[dict, str]], fetched_at: str,
            path: Path | None = None) -> int:
    """Append the lines of each due (event, phase) that PropLine lists. Returns rows written."""
    rows = []
    for event, phase in due:
        game = match_game(event, games)
        if game is None or game.get("live"):
            continue
        rows += [{"fetched_at": fetched_at, "phase": phase, "event_id": event["event_id"],
                  "propline_event_id": game.get("id"), "commence_time": event["commence_time"],
                  "home": event["home"], "away": event["away"]} | line
                 for line in parse_lines(game)]
    if not rows:
        return 0
    path = path or LINES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)
