"""A record of every FanDuel-vs-Kalshi price gap, graded like the picks.

Each snapshot logs the gaps it can see for games that have not started, one row per bet (the
first price stays, so a gap is "called" once and can't be improved later). The settle job grades
them from the game logs at a flat 1 unit. This answers the only question that matters about the
flag: over many bets, does betting the generous market actually make money?

The same pre-game rule as the picks applies: a gap is never logged once its game has started.
"""

import csv
import datetime as dt
from pathlib import Path

import pandas as pd

from ..betting.odds_math import american_to_decimal
from . import nba_paper

LOG_PATH = Path(__file__).resolve().parents[3] / "data" / "price_gap_log.csv"
COLUMNS = [
    "logged_at", "game_date", "event_id", "commence_time", "game", "player", "player_id",
    "bet", "side", "line", "book", "odds", "price_p", "reference", "reference_p", "how",
    "edge_pct", "status", "actual", "result", "pnl_units",
]
KEY = ["event_id", "player_id", "side", "line", "book"]


def _key(row) -> tuple:
    return (str(row["event_id"]), int(row["player_id"]), str(row["side"]),
            round(float(row["line"]), 2), str(row["book"]))


def load(path: Path | None = None) -> pd.DataFrame:
    path = path or LOG_PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path).astype({"status": object, "result": object})


def save(log: pd.DataFrame, path: Path | None = None) -> None:
    path = path or LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    log.to_csv(path, index=False)


def rows_to_log(gaps: pd.DataFrame, ledger: pd.DataFrame, game_date: str,
                now: dt.datetime) -> list[dict]:
    """The gaps worth logging now: each with its game's start time and date, and only for
    games that have not started."""
    starts = ledger.drop_duplicates("event_id").set_index("event_id")["commence_time"].to_dict()
    rows = []
    for _, gap in gaps.iterrows():
        commence = starts.get(gap["event_id"])
        if commence is None:
            continue
        if pd.Timestamp(commence) <= pd.Timestamp(now):
            continue                                   # the game has started: too late to call it
        rows.append({
            "logged_at": now.isoformat(), "game_date": game_date, "event_id": gap["event_id"],
            "commence_time": commence, "game": gap["Game"], "player": gap["Player"],
            "player_id": int(gap["player_id"]), "bet": gap["Bet"], "side": gap["Side"],
            "line": float(gap["line"]), "book": gap["Book"], "odds": float(gap["Odds"]),
            "price_p": round(float(gap["Price says %"]) / 100.0, 6),
            "reference": gap["Reference"], "reference_p": round(float(gap["Reference %"]) / 100.0, 6),
            "how": gap["How"], "edge_pct": round(float(gap["Edge %"]), 4),
            "status": "pending", "actual": None, "result": None, "pnl_units": None})
    return rows


def append(rows: list[dict], path: Path | None = None) -> int:
    """Add gaps not already logged for the same bet. Returns how many were new."""
    path = path or LOG_PATH
    seen = {_key(r) for r in load(path).to_dict("records")}
    fresh = []
    for row in rows:
        if _key(row) not in seen:
            seen.add(_key(row))
            fresh.append(row)
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerows(fresh)
    return len(fresh)


def won(side: str, line: float, actual: float) -> bool:
    """Over: more than the line. Under: fewer. "25+": at least 25."""
    if side == "Over":
        return actual > line
    if side == "Under":
        return actual < line
    return actual >= int(str(side).rstrip("+"))


def settle(log: pd.DataFrame, games: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """Grade pending gaps from the game logs (player_id, game_date, pts) at a flat 1 unit. A player
    with no game that day is a void once the day has passed and the logs reach it."""
    out = log.copy().astype({"status": object, "result": object})
    points = {(int(r.player_id), r.game_date.strftime("%Y-%m-%d")): float(r.pts)
              for r in games.itertuples()}
    logged_through = nba_paper.latest_logged(games)
    for index in out.index[out["status"] == "pending"]:
        row = out.loc[index]
        actual = points.get((int(row["player_id"]), str(row["game_date"])))
        if actual is None:
            if nba_paper.can_void(str(row["game_date"]), today, logged_through):
                out.loc[index, ["status", "pnl_units"]] = ["void", 0.0]
            continue
        hit = won(row["side"], float(row["line"]), actual)
        out.loc[index, ["status", "actual", "result"]] = ["settled", actual, "win" if hit else "loss"]
        out.loc[index, "pnl_units"] = american_to_decimal(float(row["odds"])) - 1.0 if hit else -1.0
    return out


def summary(log: pd.DataFrame) -> dict[str, dict]:
    """Logged, graded, record, units and return, overall and split by how the bets were
    matched: {"all": {...}, "exact": {...}, "estimated": {...}}."""
    def facts(part: pd.DataFrame) -> dict:
        graded = part[part["status"] == "settled"]
        units = float(pd.to_numeric(graded["pnl_units"], errors="coerce").sum())
        wins = int((graded["result"] == "win").sum())
        return {"logged": len(part), "graded": len(graded),
                "record": f"{wins}-{len(graded) - wins}", "units": units,
                "roi_pct": units / len(graded) * 100.0 if len(graded) else 0.0}
    out = {"all": facts(log)}
    for how in ("exact", "estimated"):
        out[how] = facts(log[log["how"] == how])
    return out
