"""FanDuel and DraftKings player-prop lines from PropLine (prop-line.com), archived as a
second source.

The Odds API's free plan only stretches to FanDuel's points lines. PropLine's free plan
(1,000 requests a day, reset at 00:00 UTC) returns every NBA game's points, rebounds,
assists and threes lines from both books in one request, so the snapshot job makes one
call per run. The lines are kept in their own file. FanDuel's rebounds, assists and
threes lines are also priced into the ledger (book "fanduel" with their own stat); points
stay with The Odds API, so the published FanDuel points record is unchanged.

Since 2026-11-25 the request names no bookmakers, so it returns every book PropLine carries
(checked that day: about 30 with main player lines, among them Pinnacle, Novig, ProphetX,
BetRivers, Fanatics, Hard Rock, Kalshi, Polymarket and the pick'em apps) in the same one
request, and every book's main lines are archived for the +EV screen (tracking/ev_screen).
Readers that predate that keep seeing FanDuel and DraftKings only (load_snapshots' default).

Checked against the live API on 2026-11-22: its FanDuel points lines matched The Odds
API's exactly on all 14 players of a game pulled at the same moment.

The key is read from PROPLINE_API_KEY or data/propline_key.txt (git-ignored). It travels
in a header, never the URL, and error messages never include it.
"""

import csv
import datetime as dt
import os
import re
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parents[3] / "data"
KEY_PATH = DATA / "propline_key.txt"
LINES_PATH = DATA / "nba_propline_lines.csv"
BASE = "https://api.prop-line.com/v1"
SPORT_KEY = "basketball_nba"
FANDUEL = "fanduel"
BOOKS = (FANDUEL, "draftkings")    # the books everything before the +EV screen reads
MARKETS = {"player_points": "points", "player_rebounds": "rebounds",
           "player_assists": "assists", "player_threes": "threes"}
GAME_MARKETS = ("h2h", "spreads", "totals")
RUNG = re.compile(r"^\s*(\d+)\+")      # "6+ Rebounds" -> 6
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
    """Every listed NBA game with every book's main lines for the four stats. One request.
    Returns the games and the requests left today (None if PropLine did not say)."""
    key = get_api_key()
    if not key:
        raise PropLineError("No PropLine key configured")
    try:
        response = get(f"{BASE}/sports/{SPORT_KEY}/odds", headers={"X-API-Key": key},
                       params={"markets": ",".join([*MARKETS, *GAME_MARKETS])},
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


def parse_lines(game: dict, books: tuple[str, ...] | None = BOOKS) -> list[dict]:
    """One row per book, stat, player and line, pairing Over with Under. Main lines only:
    the "X+" milestone ladders are skipped, and so are books outside `books` (None keeps
    every book). Prediction markets list several "main" numbers per player; each is a row."""
    rows: dict[tuple, dict] = {}
    for listing in game.get("bookmakers", []):
        book = listing.get("key")
        if not book or (books is not None and book not in books):
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


def new_fanduel_lines(game: dict) -> dict[str, list[dict]]:
    """FanDuel's main lines for the stats The Odds API does not give us (everything but
    points), by stat, in the shape the ledger prices. Lines missing a side are left out.
    Points stay with The Odds API, so the published FanDuel points record is unchanged."""
    by_stat: dict[str, list[dict]] = {}
    for row in parse_lines(game):
        if (row["book"] == FANDUEL and row["stat"] != "points"
                and None not in (row["over_odds"], row["under_odds"])):
            by_stat.setdefault(row["stat"], []).append(
                {key: row[key] for key in ("player", "line", "over_odds", "under_odds")})
    return by_stat


def milestone_fanduel_lines(game: dict) -> dict[str, list[dict]]:
    """FanDuel's "X+" rungs for every stat, by stat, as {player, line, over_odds} with line
    half a point under the rung (6+ is 5.5). These markets list one side only and name the
    rung in the outcome ("6+ Rebounds")."""
    by_stat: dict[str, list[dict]] = {}
    for listing in game.get("bookmakers", []):
        if listing.get("key") != FANDUEL:
            continue
        for market in listing.get("markets", []):
            stat = MARKETS.get(market.get("key"))
            if stat is None or market.get("line_type") != "milestone":
                continue
            for outcome in market.get("outcomes", []):
                rung = RUNG.match(str(outcome.get("name") or ""))
                player, price = outcome.get("description"), outcome.get("price")
                if rung and player and price is not None:
                    by_stat.setdefault(stat, []).append(
                        {"player": player, "line": int(rung.group(1)) - 0.5, "over_odds": price})
    return by_stat


def load_snapshots(path: Path | None = None,
                   books: tuple[str, ...] | None = BOOKS) -> pd.DataFrame:
    """The archive, limited to `books` (None for every book). The default keeps the closing
    prices the ledger settles against exactly as they were before every book was archived."""
    path = path or LINES_PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    table = pd.read_csv(path)
    return table if books is None else table[table["book"].isin(books)].reset_index(drop=True)


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


def snapshot_rows(games: list[dict], due: list[tuple[dict, str]], fetched_at: str) -> list[dict]:
    """Every book's main lines for each due (event, phase) that PropLine lists pregame, in
    the archive's shape."""
    rows = []
    for event, phase in due:
        game = match_game(event, games)
        if game is None or game.get("live"):
            continue
        rows += [{"fetched_at": fetched_at, "phase": phase, "event_id": event["event_id"],
                  "propline_event_id": game.get("id"), "commence_time": event["commence_time"],
                  "home": event["home"], "away": event["away"]} | line
                 for line in parse_lines(game, books=None)]
    return rows


def archive(games: list[dict], due: list[tuple[dict, str]], fetched_at: str,
            path: Path | None = None) -> int:
    """Append every book's lines for each due (event, phase) that PropLine lists. Returns
    rows written."""
    rows = snapshot_rows(games, due, fetched_at)
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
