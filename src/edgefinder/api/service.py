"""What the web app shows, computed from the same functions the Streamlit app uses.

Nothing here prices, projects or grades anything new: it gathers the ledger, the legs, the ideas
and the price gaps that `tracking/` already produces and shapes them for the API. Results are
cached for a short time so a page of taps doesn't re-read the files each time.
"""

import datetime as dt
import math
import time
from collections.abc import Callable

import pandas as pd

from ..betting import correlated
from ..data import job_health, nba_stats
from ..data.nba_snapshot_plan import EASTERN
from ..models import nba_stat_model
from ..tracking import nba_alt, nba_paper, nba_parlay, nba_view, price_gaps

CACHE_SECONDS = 60
IDEAS_SHOWN = 3
BOOK_NAMES = {"fanduel": "FanDuel", "kalshi": "Kalshi"}
_cache: dict[tuple, tuple[float, object]] = {}


class NotFound(ValueError):
    """The day, price source or model asked for has no lines."""


def cached(key: tuple, compute: Callable, seconds: float = CACHE_SECONDS):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < seconds:
        return hit[1]
    value = compute()
    _cache[key] = (time.monotonic(), value)
    return value


def clear_cache() -> None:
    _cache.clear()


# ---- data, swappable in tests ------------------------------------------------------------------

def load_ledger() -> pd.DataFrame:
    return cached(("ledger",), nba_paper.load_ledger)


def load_alt() -> pd.DataFrame:
    return cached(("alt",), nba_alt.load_ledger)


def load_games() -> pd.DataFrame:
    """Two seasons of game logs, so "last 10" still means ten games early in a season."""
    def read() -> pd.DataFrame:
        today = dt.date.today()
        try:
            return pd.concat([nba_stats.load_season(s, today=today)
                              for s in nba_stats.recent_seasons(today, 2)], ignore_index=True)
        except nba_stats.NbaDataError:
            return pd.DataFrame()
    return cached(("games",), read, 600)


def today() -> dt.date:
    return dt.datetime.now(EASTERN).date()


# ---- helpers ---------------------------------------------------------------------------------

def _num(value, digits: int = 2):
    """A JSON-safe number: None for missing."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else round(number, digits)


def _averages() -> dict:
    games = load_games()
    return nba_parlay.player_averages(games) if not games.empty else {}


def _minutes() -> dict[int, float]:
    return {pid: s["minutes"][1] for pid, s in _averages().items() if "minutes" in s}


def _teams() -> dict[int, str]:
    games = load_games()
    return nba_parlay.player_teams(games) if not games.empty else {}


def _short(game: str) -> str:
    return nba_view.short_game(game)


# ---- the day's market --------------------------------------------------------------------------

def days() -> list[dict]:
    now = today()
    return [{"date": d, "label": nba_view.day_label(d, now)}
            for d in nba_view.game_dates(load_ledger())]


def _choose(date: str | None, book: str | None, model: str | None) -> tuple[str, str, str, dict]:
    ledger = load_ledger()
    dates = nba_view.game_dates(ledger)
    if not dates:
        raise NotFound("no lines recorded yet")
    date = date or dates[0]
    found = nba_parlay.sources(ledger, date)
    if not found:
        raise NotFound(f"no lines on {date}")
    books = nba_parlay.books_on(found)
    book = book if book in found else books[0]
    versions = nba_parlay.model_versions(found, book)
    model = model if model in versions else versions[0]
    return date, book, model, found


def candidates(date: str | None, book: str | None, model: str | None) -> tuple[pd.DataFrame, dict]:
    date, book, model, found = _choose(date, book, model)

    def build() -> pd.DataFrame:
        return nba_parlay.all_candidates(load_ledger(), load_alt(), date, model, book, found,
                                         _minutes())
    table = cached(("candidates", date, book, model), build)
    return table, {"date": date, "book": book, "model": model, "found": found}


def _leg(index: int, row: pd.Series, averages: dict) -> dict:
    stat = row["stat_key"]
    pair = averages.get(int(row["player_id"]), {}).get(nba_stat_model.STATS[stat].column)
    return {
        "id": int(index), "player": row["Player"], "player_id": int(row["player_id"]),
        "photo": nba_parlay.headshot_url(row["player_id"]), "game": row["Game"],
        "game_short": _short(row["Game"]), "stat": stat, "stat_label": row["Stat"],
        "side": row["Side"], "line": _num(row["line"], 1),
        "bet": row["Leg"].split(" · ", 1)[-1], "odds": int(row["Odds"]),
        "model_pct": _num(row["Model %"], 1), "market_pct": _num(row["Market %"], 1),
        "chance_pct": _num(row["Blended %"], 1), "ev_pct": _num(row["Leg EV %"], 1),
        "average": None if pair is None else {"season": _num(pair[0], 1),
                                              "last10": _num(pair[1], 1)},
    }


def board(date: str | None = None, book: str | None = None, model: str | None = None) -> dict:
    """Everything the Parlay screen opens with."""
    table, chosen = candidates(date, book, model)
    found = chosen["found"]
    averages = _averages()
    legs = [_leg(i, row, averages) for i, row in table.iterrows()]
    games = [{"game": g, "short": _short(g)} for g in sorted(table["Game"].unique())]
    gaps = gaps_for(chosen["date"], chosen["book"], table)
    return {
        "date": chosen["date"], "day_label": nba_view.day_label(chosen["date"], today()),
        "days": days(),
        "book": chosen["book"],
        "books": [{"id": b, "name": BOOK_NAMES.get(b, b)} for b in nba_parlay.books_on(found)],
        "model": chosen["model"],
        "models": [{"id": v, "short": nba_parlay.short_model_name(v),
                    "name": nba_parlay.model_name(v)}
                   for v in nba_parlay.model_versions(found, chosen["book"])],
        "summary": {"games": len(games),
                    "props": int(table[["player_id", "stat_key"]].drop_duplicates().shape[0]),
                    "gaps": len(gaps)},
        "games": games, "legs": legs, "gaps": gaps,
        "styles": list(nba_parlay.STYLES), "default_style": nba_parlay.DEFAULT_STYLE,
    }


def gaps_for(date: str, book: str, table: pd.DataFrame) -> list[dict]:
    found = cached(("gaps", date),
                   lambda: price_gaps.find_gaps(load_ledger(), load_alt(), date))
    out = []
    for _, row in found[found["Book"] == book].iterrows():
        index = price_gaps.candidate_index(table, row)
        out.append({"leg_id": index, "player": row["Player"], "player_id": int(row["player_id"]),
                    "photo": nba_parlay.headshot_url(row["player_id"]),
                    "game_short": _short(row["Game"]), "bet": row["Bet"],
                    "odds": int(row["Odds"]), "edge_pct": _num(row["Edge %"], 1),
                    "price_pct": _num(row["Price says %"], 1),
                    "reference": row["Reference"], "reference_pct": _num(row["Reference %"], 1),
                    "estimated": row["How"] == "estimated"})
    return out


def ideas(date: str | None, book: str | None, model: str | None, style: str,
          game: str | None = None) -> list[dict]:
    """Suggested slips for a style; for one game when `game` is given (same-game slips)."""
    if style not in nba_parlay.STYLES:
        raise NotFound(f"unknown style {style}")
    table, chosen = candidates(date, book, model)
    pool = table if not game else table[table["Game"] == game]

    def search() -> pd.DataFrame:
        return nba_parlay.suggest_parlays(
            pool, top=IDEAS_SHOWN, min_chance=nba_parlay.STYLES[style],
            min_profit=nba_parlay.MIN_PROFIT[style], real_leg_decimal=nba_parlay.REAL_LEG_DECIMAL,
            one_per_game=not game, bench=nba_parlay.bench_players(_averages()))
    slips = cached(("ideas", chosen["date"], chosen["book"], chosen["model"], style, game), search,
                   300)
    return [{"legs": [int(i) for i in row["bets"]], "chance_pct": _num(row["Chance %"], 1),
             "pays": _num(row["Pays"] + 1.0, 2), "ev_pct": _num(row["EV %"], 1)}
            for _, row in slips.iterrows()]


def price_slip(date: str | None, book: str | None, model: str | None, leg_ids: list[int],
               stake: float) -> dict:
    """The slip's chance, payout and what it is worth, the same maths as the Parlay screen."""
    table, _ = candidates(date, book, model)
    missing = [i for i in leg_ids if i not in table.index]
    if missing:
        raise NotFound(f"unknown legs {missing}")
    if not leg_ids:
        return {"legs": 0}
    chosen = table.loc[leg_ids]
    summary = correlated.summarise(nba_parlay.to_legs(chosen, _teams()))
    outcomes = nba_parlay.stake_outcomes(stake, summary["decimal_odds"], summary["ev_per_unit"])
    p = summary["joint_probability"]
    return {
        "legs": len(leg_ids), "chance_pct": _num(p * 100, 1), "one_in": nba_parlay.one_in(p),
        "independent_pct": _num(summary["independent_probability"] * 100, 1),
        "decimal": _num(summary["decimal_odds"], 3), "fair_american": summary["fair_american"],
        "ev_pct": _num(summary["ev_per_unit"] * 100, 1),
        "verdict": nba_parlay.verdict(summary["ev_per_unit"]).replace("\\$", "$"),
        "stake": _num(stake, 2), "to_win": _num(outcomes["profit_if_wins"], 2),
        "total_return": _num(outcomes["total_return"], 2),
        "expected": _num(outcomes["expected_profit"], 2),
    }


def health() -> dict:
    beats, now = job_health.load(), dt.datetime.now(dt.timezone.utc)
    snapshot = job_health.snapshot_health(beats, now)
    settle = job_health.settle_health(beats, now)
    return {"snapshot": {"level": snapshot.level, "text": snapshot.text},
            "settle": {"level": settle.level, "text": settle.text}}
