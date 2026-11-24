"""Each game's moneyline from PropLine, archived beside the prop lines, and the market's
no-vig win chance for each side.

PropLine returns FanDuel's and DraftKings' full-game moneylines ("h2h") in the same bulk
request the snapshot job already makes for player props, so they cost no extra request.
Outcomes are matched by their `side` ("home" / "away"), since the books spell team names
differently ("LA Lakers"). These prices are for display only: they never enter the
published record, the X posts or the slip trials.
"""

import csv
from pathlib import Path

import pandas as pd

from ..betting import odds_math
from . import propline

MONEYLINES_PATH = propline.DATA / "nba_moneylines.csv"
MARKET = "h2h"
COLUMNS = ["fetched_at", "phase", "event_id", "propline_event_id", "commence_time", "home",
           "away", "book", "away_odds", "home_odds", "changed_at"]


def parse(game: dict) -> list[dict]:
    """One row per book with both sides of its full-game moneyline."""
    rows = []
    for listing in game.get("bookmakers") or []:
        book = listing.get("key")
        if book not in propline.BOOKS:
            continue
        for market in listing.get("markets") or []:
            if (market.get("key") != MARKET or market.get("line_type") != "main"
                    or market.get("period")):
                continue
            outcomes = market.get("outcomes") or []
            prices = {o.get("side"): o.get("price") for o in outcomes}
            if prices.get("away") is None or prices.get("home") is None:
                continue
            changed = max(filter(None, (o.get("last_change_at") for o in outcomes)), default=None)
            rows.append({"book": book, "away_odds": prices["away"], "home_odds": prices["home"],
                         "changed_at": changed})
            break
    return rows


def win_pcts(away_odds: float, home_odds: float) -> tuple[float, float]:
    """Each side's win chance in percent with the book's margin taken out."""
    away, home = odds_math.devig_two_way(odds_math.implied_prob(away_odds),
                                         odds_math.implied_prob(home_odds))
    return round(away * 100, 1), round(home * 100, 1)


def archive(games: list[dict], due: list[tuple[dict, str]], fetched_at: str,
            path: Path | None = None) -> int:
    """Append the moneylines of each due (event, phase) PropLine lists before tip-off.
    Returns rows written."""
    rows = []
    for event, phase in due:
        game = propline.match_game(event, games)
        if game is None or game.get("live"):
            continue
        rows += [{"fetched_at": fetched_at, "phase": phase, "event_id": event["event_id"],
                  "propline_event_id": game.get("id"), "commence_time": event["commence_time"],
                  "home": event["home"], "away": event["away"]} | line for line in parse(game)]
    if not rows:
        return 0
    path = path or MONEYLINES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def load(path: Path | None = None) -> pd.DataFrame:
    path = path or MONEYLINES_PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path)


def latest(frame: pd.DataFrame, book: str) -> dict[str, dict]:
    """Each event's most recent moneyline: the chosen book's when it has one, else the
    other book's. Keyed by event id, with each side's no-vig win chance."""
    if frame.empty:
        return {}
    ordered = frame.assign(_mine=frame["book"] == book).sort_values(["_mine", "fetched_at"])
    found = {}
    for row in ordered.drop_duplicates("event_id", keep="last").itertuples(index=False):
        away_pct, home_pct = win_pcts(row.away_odds, row.home_odds)
        found[str(row.event_id)] = {"book": row.book, "away_odds": int(row.away_odds),
                                    "home_odds": int(row.home_odds), "away_pct": away_pct,
                                    "home_pct": home_pct, "as_of": row.fetched_at}
    return found
