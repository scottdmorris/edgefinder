"""The +EV screen's data: lines one book prices better than the other books' fair consensus, from
the latest PropLine snapshot of each game that has not started, and the paper record of past
flags. Read-only. A paper experiment: it shows where prices disagree, never what to bet."""

import datetime as dt

import pandas as pd

from ..data import propline
from ..data.nba_snapshot_plan import tip_date
from ..tracking import ev_log, ev_screen, nba_parlay, nba_view
from . import service

LINES_SHOWN = 40
STAT_WORDS = {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes": "threes"}


def load_snapshots() -> pd.DataFrame:
    return service.cached(("propline_all",), lambda: propline.load_snapshots(books=None))


def load_log() -> pd.DataFrame:
    return service.cached(("ev_log",), ev_log.load)


def _valid_date(date: str) -> str:
    try:
        return dt.date.fromisoformat(date).isoformat()
    except ValueError:
        raise service.NotFound(f"not a date: {date[:12]}") from None


def _photo(player_id) -> str | None:
    pid = ev_log._player_id(player_id)
    return nba_parlay.headshot_url(pid) if pid is not None else None


def _line(flag: dict, fetched: dict) -> dict:
    return {"player": flag["player"], "photo": _photo(flag["player_id"]),
            "game_short": nba_view.short_game(flag["game"]), "stat": flag["stat"],
            "bet": f"{flag['side']} {flag['line']:g} {STAT_WORDS.get(flag['stat'], flag['stat'])}",
            "book": flag["book"], "book_name": ev_screen.book_name(flag["book"]),
            "odds": int(flag["odds"]), "fair_odds": int(flag["fair_odds"]),
            "fair_pct": service._num(flag["fair_p"] * 100, 1),
            "edge_pct": service._num(flag["edge_pct"], 1), "books": int(flag["books"]),
            "fetched_at": fetched.get(flag["event_id"])}


def _record() -> dict:
    s = ev_log.summary(load_log())["all"]
    return {key: s[key] if not isinstance(s[key], float) else service._num(s[key], 2)
            for key in ("logged", "graded", "record", "units", "roi_pct", "clv_novig_n",
                        "avg_clv_novig_pct")}


def ev(date: str | None = None) -> dict:
    date = _valid_date(date) if date else service.today().isoformat()
    lines = ev_screen.latest(load_snapshots(), now=service.now())
    if not lines.empty:
        lines = lines[[tip_date(row) == date for row in lines[["commence_time"]].to_dict("records")]]
    flags = ev_screen.screen(lines)
    fetched = lines.groupby("event_id")["fetched_at"].max().to_dict() if not lines.empty else {}
    return {"date": date, "min_edge_pct": ev_screen.MIN_EDGE * 100,
            "min_books": ev_screen.MIN_BOOKS, "flagged": len(flags),
            "books": int(lines["book"].nunique()) if not lines.empty else 0,
            "lines": [_line(f, fetched) for f in flags.head(LINES_SHOWN).to_dict("records")],
            "record": _record()}
