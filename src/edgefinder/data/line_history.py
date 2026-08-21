"""Append-only history of every FanDuel snapshot we fetch.

Two uses: showing how a line has moved, and recovering an approximate
closing line (the last snapshot before first pitch) for CLV — the free
API tier has no historical odds, so we build our own archive as we go.
"""

import csv
import datetime as dt
from pathlib import Path

import pandas as pd

HISTORY_PATH = Path(__file__).resolve().parents[3] / "data" / "line_history.csv"

COLUMNS = [
    "fetched_at", "sport_key", "home", "away", "commence_time",
    "home_ml", "away_ml", "draw_ml", "total_line", "over_odds", "under_odds",
]


def append_snapshots(sport_key: str, events: list[dict]) -> None:
    if not events:
        return
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not HISTORY_PATH.exists()
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    with HISTORY_PATH.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        for event in events:
            writer.writerow({
                "fetched_at": fetched_at,
                "sport_key": sport_key,
                "home": event.get("home"),
                "away": event.get("away"),
                "commence_time": event.get("commence_time"),
                "home_ml": event.get("home_ml"),
                "away_ml": event.get("away_ml"),
                "draw_ml": event.get("draw_ml"),
                "total_line": event.get("total_line"),
                "over_odds": event.get("over_odds"),
                "under_odds": event.get("under_odds"),
            })


def load_history() -> pd.DataFrame:
    if not HISTORY_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(HISTORY_PATH)


# schedule time (MLB API) and odds commence time can differ by minutes;
# same-matchup games on consecutive days differ by ~24h
MATCH_WINDOW_SECONDS = 6 * 3600


def _parse(timestamp) -> dt.datetime | None:
    if not isinstance(timestamp, str) or not timestamp:
        return None
    try:
        return dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def history_for(home: str, away: str, commence_time: str | None = None) -> pd.DataFrame:
    """Snapshots for one matchup, optionally narrowed to the game whose
    start time is near commence_time (timestamps from different APIs
    never match exactly, so proximity beats equality)."""
    df = load_history()
    df = df[(df["home"] == home) & (df["away"] == away)]
    target = _parse(commence_time)
    if target is not None and not df.empty:
        def is_same_game(value) -> bool:
            parsed = _parse(value)
            if parsed is None:
                return False
            return abs((parsed - target).total_seconds()) <= MATCH_WINDOW_SECONDS
        df = df[df["commence_time"].apply(is_same_game)]
    return df.sort_values("fetched_at").reset_index(drop=True)


def closing_snapshot(home: str, away: str, commence_time: str | None) -> dict | None:
    """Last snapshot taken before the game started — our best proxy for
    the closing line."""
    df = history_for(home, away, commence_time)
    target = _parse(commence_time)
    if target is not None and not df.empty:
        def before_start(value) -> bool:
            parsed = _parse(value)
            return parsed is not None and parsed <= target
        df = df[df["fetched_at"].apply(before_start)]
    if df.empty:
        return None
    return df.iloc[-1].to_dict()
