"""Pregame NBA full-game spreads and totals from the existing PropLine snapshot."""

import datetime as dt
import math
from pathlib import Path

import pandas as pd

from . import propline, safe_write

LINES_PATH = propline.DATA / "nba_game_lines.csv"
COLUMNS = ["event_id", "book", "fetched_at", "commence_time", "phase", "home_spread", "total"]


def parse(game: dict) -> list[dict]:
    rows = []
    for listing in game.get("bookmakers") or []:
        book = listing.get("key")
        if book not in propline.BOOKS:
            continue
        spread, total = None, None
        for market in listing.get("markets") or []:
            if (market.get("line_type") != "main" or market.get("period")
                    or market.get("team") or market.get("suspended_at")):
                continue
            outcomes = market.get("outcomes") or []
            if market.get("key") == "spreads":
                points = {o.get("side"): o.get("point") for o in outcomes}
                home, away = points.get("home"), points.get("away")
                if isinstance(home, (int, float)) and math.isfinite(home) and away == -home:
                    spread = home
            elif market.get("key") == "totals":
                points = {o.get("name"): o.get("point") for o in outcomes}
                over = points.get("Over")
                if isinstance(over, (int, float)) and math.isfinite(over) and over > 0 and points.get("Under") == over:
                    total = over
        if spread is not None:
            rows.append({"book": book, "home_spread": spread, "total": total})
    return rows


def load(path: Path | None = None) -> pd.DataFrame:
    path = path or LINES_PATH
    return pd.read_csv(path, dtype={"event_id": str}) if path.exists() else pd.DataFrame(columns=COLUMNS)


def archive(games: list[dict], due: list[tuple[dict, str]], fetched_at: str,
            path: Path | None = None) -> int:
    captured = dt.datetime.fromisoformat(fetched_at)
    rows = []
    for event, phase in due:
        game = propline.match_game(event, games)
        if game is None or game.get("live"):
            continue
        tip = min(event["commence_time"], game["commence_time"], key=dt.datetime.fromisoformat)
        if captured >= dt.datetime.fromisoformat(tip):
            continue
        rows.extend({"event_id": event["event_id"], "fetched_at": fetched_at,
                     "commence_time": tip, "phase": phase} | line for line in parse(game))
    if rows:
        path = path or LINES_PATH
        with safe_write.locked(path):
            old = load(path)
            new = pd.DataFrame(rows, columns=COLUMNS)
            safe_write.write_csv(pd.concat([old, new], ignore_index=True) if not old.empty else new, path)
    return len(rows)


def latest(frame: pd.DataFrame, book: str, event_ids: list[str]) -> dict | None:
    rows = frame[frame["event_id"].astype(str).isin(event_ids)]
    if rows.empty:
        return None
    fetched = pd.to_datetime(rows["fetched_at"], utc=True, format="mixed", errors="coerce")
    tip = pd.to_datetime(rows["commence_time"], utc=True, format="mixed", errors="coerce")
    ordered = rows.assign(_time=fetched, _preferred=rows["book"].eq(book))[fetched < tip]
    if ordered.empty:
        return None
    quote = ordered.sort_values(["_preferred", "_time"]).iloc[-1]
    return {"book": quote["book"], "home_spread": float(quote["home_spread"]),
            "total": float(quote["total"]) if pd.notna(quote["total"]) else None, "as_of": quote["fetched_at"]}
