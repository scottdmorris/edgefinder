"""A paper record of every +EV flag (tracking/ev_screen), graded like the price gaps.

Each PropLine snapshot logs the flags it sees for games that have not started, one row per
book, player, stat, side and number; the first price stays, so a flag is called once. The settle
job grades them from the game logs at a flat 1 unit and measures each against the market's fair
close (every book's last pregame price on that number, devigged and averaged). Over many flags
this answers whether the screen finds bets that actually win, not just prices that disagree.

Nothing here is published or posted: the public record stays FanDuel points picks.
"""

import datetime as dt
from pathlib import Path

import pandas as pd

from ..data import safe_write
from ..models import nba_stat_model
from . import closing, ev_screen, gap_log

LOG_PATH = Path(__file__).resolve().parents[3] / "data" / "ev_log.csv"
COLUMNS = [
    "logged_at", "game_date", "event_id", "commence_time", "game", "player", "player_id", "stat",
    "bet", "side", "line", "book", "odds", "fair_p", "fair_odds", "edge_pct", "books",
    "status", "actual", "result", "pnl_units", "clv_novig_pct",
]


def _key(row) -> tuple:
    return (str(row["event_id"]), int(row["player_id"]), str(row["stat"]), str(row["side"]),
            round(float(row["line"]), 2), str(row["book"]))


def _player_id(value) -> int | None:
    """PropLine's "nba:1628389" (or a plain number) as the game logs' integer id."""
    text = str(value).rsplit(":", 1)[-1]
    return int(text) if text.isdigit() else None


def load(path: Path | None = None) -> pd.DataFrame:
    path = path or LOG_PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path).reindex(columns=COLUMNS).astype({"status": object, "result": object})


def save(log: pd.DataFrame, path: Path | None = None) -> None:
    safe_write.write_csv(log, path or LOG_PATH)


def rows_to_log(flags: pd.DataFrame, now: dt.datetime, tip_date) -> list[dict]:
    """The flags as ledger rows: only games that have not started and players with an NBA id.
    `tip_date(event)` gives a game's date from its {"commence_time"}."""
    rows = []
    for flag in flags.to_dict("records"):
        player_id = _player_id(flag["player_id"])
        if player_id is None or pd.Timestamp(flag["commence_time"]) <= pd.Timestamp(now):
            continue
        rows.append(flag | {
            "logged_at": now.isoformat(), "game_date": tip_date(flag),
            "player_id": player_id, "bet": f"{flag['side']} {flag['line']:g}",
            "status": "pending", "actual": None, "result": None, "pnl_units": None,
            "clv_novig_pct": None})
    return rows


def append(rows: list[dict], path: Path | None = None) -> int:
    """Add flags not already logged for the same bet at the same book. Returns how many."""
    path = path or LOG_PATH
    with safe_write.locked(path):         # never while a settle is rewriting the file
        log = load(path)
        seen = {_key(r) for r in log.to_dict("records")}
        fresh = []
        for row in rows:
            if _key(row) not in seen:
                seen.add(_key(row))
                fresh.append({column: row.get(column) for column in COLUMNS})
        if fresh:
            save(pd.concat([log, pd.DataFrame(fresh, columns=COLUMNS)], ignore_index=True)
                 if not log.empty else pd.DataFrame(fresh, columns=COLUMNS), path)
        return len(fresh)


def settle(log: pd.DataFrame, games: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """Grade pending flags from the game logs, each by its own stat, as gap_log grades points."""
    out = log.copy().astype({"status": object, "result": object})
    for stat, part in out.groupby("stat"):
        column = nba_stat_model.STATS[stat].column if stat in nba_stat_model.STATS else None
        if column is None or column not in games.columns:
            continue                                   # the game logs don't cover this stat
        graded = gap_log.settle(part, games.assign(pts=games[column]), today)
        out.loc[graded.index] = graded
    return out


def attach_closing(log: pd.DataFrame, snapshots: pd.DataFrame | None) -> pd.DataFrame:
    """A copy with each flag's value against the market's fair close: every book's (pick'em
    apps aside) last late price on the same number, devigged and averaged."""
    out = log.copy()
    out["clv_novig_pct"] = None
    if snapshots is None or snapshots.empty or out.empty:
        return out
    books = snapshots[~snapshots["book"].isin(ev_screen.PICKEM)]
    fair = closing.fair_closes(*[group for _, group in books.groupby("book")], events=out)
    for index, row in out.iterrows():
        key = (str(row["event_id"]), str(row["player"]), str(row["stat"]), float(row["line"]))
        if key in fair:
            out.loc[index, "clv_novig_pct"] = closing.novig_clv_pct(
                row["side"] == "Over", row["odds"], fair[key])
    return out


def summary(log: pd.DataFrame) -> dict:
    """Logged, graded, record, units, return and fair-close value: overall and by stat."""
    def facts(part: pd.DataFrame) -> dict:
        return gap_log.summary(part, splits=())["all"]
    return {"all": facts(log),
            "by_stat": {stat: facts(part) for stat, part in log.groupby("stat")}}
