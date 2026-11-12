"""What the web app shows, computed from the same functions the Streamlit app uses.

Nothing here prices, projects or grades anything new: it gathers the ledger, the legs, the ideas
and the price gaps that `tracking/` already produces and shapes them for the API. Results are
cached for a short time so a page of taps doesn't re-read the files each time.
"""

import datetime as dt
import hashlib
import json
import math
import time
from collections.abc import Callable

import pandas as pd

from ..betting import correlated, odds_math
from ..data import job_health, nba_stats
from ..data.nba_snapshot_plan import EASTERN
from ..models import nba_stat_model
from ..tracking import nba_alt, nba_paper, nba_parlay, nba_view, price_gaps

CACHE_SECONDS = 60
IDEAS_SHOWN = 3
STEADY_GAMES = 20             # the same window the season backtest measured
STEADY_MIN_RATE = 0.9
STEADY_SHOWN = 8
RECOMMEND_MIN_LINES = 100     # graded lines every model priced before one is recommended
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
    model = model if model in versions else recommended_model(versions, book)
    return date, book, model, found


def model_standing(book: str) -> dict[str, dict]:
    """Each model's graded points record on a price source, and its accuracy on the lines every
    model priced (lower is better), so no model is flattered by an easier set of lines."""
    def build() -> dict[str, dict]:
        ledger = load_ledger()
        if ledger.empty:
            return {}
        head_to_head = nba_paper.compare_versions(ledger, stat="points", book=book)
        out = {}
        for version in nba_paper.scope(ledger, book=book)["model_version"].dropna().unique():
            picks = nba_paper.summary(ledger, model_version=version, stat="points", book=book)
            scored = version in head_to_head.index
            out[version] = {
                "record": picks["record"], "settled": picks["settled"],
                "lines": int(head_to_head.loc[version, "n"]) if scored else 0,
                "brier": float(head_to_head.loc[version, "brier_model"]) if scored else None}
        return out
    return cached(("standing", book), build, 300)


def recommended_model(versions: list[str], book: str) -> str:
    """The most accurate model so far on this source, once enough lines are graded; until
    then the newest."""
    standing = model_standing(book)
    scored = [v for v in versions if standing.get(v, {}).get("brier") is not None
              and standing[v]["lines"] >= RECOMMEND_MIN_LINES]
    return min(scored, key=lambda v: standing[v]["brier"]) if scored else versions[0]


def quote_id(date: str, book: str, model: str, row: pd.Series) -> int:
    """A leg's identity is the bet itself, never its price: a saved slip must survive the next
    snapshot moving the odds. 52 bits, so it stays exact in JavaScript."""
    values = ["quote-v3", date, book, model, str(row["event_id"]), int(row["player_id"]),
              row["stat_key"], row["Side"], float(row["line"])]
    return int(hashlib.sha256(json.dumps(values).encode()).hexdigest()[:13], 16)


def model_short(version: str) -> str:
    return {"ewma-v1": "Recent average", "minutes-v1": "Minutes",
            "context-v1": "Context", "context-v2": "Shot profile"}.get(version, version)


def model_name(version: str) -> str:
    original = nba_parlay.model_name(version)
    return model_short(version) + (": " + original.split(": ", 1)[1] if ": " in original else "")


def candidates(date: str | None, book: str | None, model: str | None) -> tuple[pd.DataFrame, dict]:
    date, book, model, found = _choose(date, book, model)

    def build() -> pd.DataFrame:
        return nba_parlay.all_candidates(load_ledger(), load_alt(), date, model, book, found,
                                         _minutes())
    def identified() -> pd.DataFrame:
        table = build().copy()
        # Deterministic IDs, never positions: a snapshot adding or reordering rows
        # must not turn a saved selection into another bet.
        table.index = [quote_id(date, book, model, row) for _, row in table.iterrows()]
        if not table.index.is_unique:
            raise ValueError("duplicate quote identities; refresh the recorded data")
        return table
    table = cached(("candidates", date, book, model), identified)
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
        "projection": _num(row.get("projection"), 1),
        "projection_model": model_short(row.get("projection_model", "")),
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
        "models": _model_options(nba_parlay.model_versions(found, chosen["book"]), chosen["book"]),
        "summary": {"games": len(games),
                    "props": int(table[["player_id", "stat_key"]].drop_duplicates().shape[0]),
                    "gaps": len(gaps)},
        "games": games, "legs": legs, "gaps": gaps,
        "steady": steady_for(chosen["date"], table),
        "styles": list(nba_parlay.STYLES), "default_style": nba_parlay.DEFAULT_STYLE,
    }


def _model_options(versions: list[str], book: str) -> list[dict]:
    """The models to choose from, the recommended one first, each with its graded record."""
    standing, best = model_standing(book), recommended_model(versions, book)
    proven = standing.get(best, {}).get("lines", 0) >= RECOMMEND_MIN_LINES
    options = [{"id": v, "short": model_short(v), "name": model_name(v),
                "record": standing.get(v, {}).get("record"),
                "settled": standing.get(v, {}).get("settled", 0),
                "recommended": proven and v == best} for v in versions]
    return sorted(options, key=lambda option: not option["recommended"])


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


def _threshold(side: str, line: float) -> int | None:
    """The number a "yes" leg needs: over 24.5 and "25+" both mean 25. None for an under."""
    if side == "Over":
        return math.floor(line) + 1
    return int(side[:-1]) if side.endswith("+") else None


def steady_for(date: str, table: pd.DataFrame) -> list[dict]:
    """Legs a player has reached in nearly all of his last 20 games, next to what they cost.

    A convenience for building slips, not an edge: over a full season these hit about as often as
    their price said (docs/KALSHI_BACKTEST.md). One leg per player and stat, the highest number
    that still qualifies.
    """
    games = load_games()
    if games.empty or table.empty:
        return []
    before = games[games["game_date"] < pd.Timestamp(date)].sort_values("game_date")
    recent = {pid: rows.tail(STEADY_GAMES) for pid, rows in before.groupby("player_id")}
    found = []
    for index, row in table.iterrows():
        threshold = _threshold(row["Side"], float(row["line"]))
        last = recent.get(int(row["player_id"]))
        if threshold is None or last is None or len(last) < STEADY_GAMES:
            continue
        hits = int((last[nba_stat_model.STATS[row["stat_key"]].column] >= threshold).sum())
        if hits / STEADY_GAMES < STEADY_MIN_RATE:
            continue
        found.append({"leg_id": int(index), "player": row["Player"],
                      "player_id": int(row["player_id"]),
                      "photo": nba_parlay.headshot_url(row["player_id"]),
                      "game": row["Game"], "game_short": _short(row["Game"]),
                      "stat": row["stat_key"], "bet": row["Leg"].split(" · ", 1)[-1],
                      "threshold": threshold, "odds": int(row["Odds"]),
                      "hits": hits, "games": STEADY_GAMES,
                      "hit_pct": _num(100 * hits / STEADY_GAMES, 1),
                      "price_pct": _num(100 * odds_math.implied_prob(row["Odds"]), 1)})
    best: dict[tuple, dict] = {}
    for item in sorted(found, key=lambda i: (-i["threshold"], -i["odds"])):
        best.setdefault((item["player_id"], item["stat"]), item)
    ranked = sorted(best.values(), key=lambda i: (-i["hits"], i["price_pct"], i["player"]))
    return ranked[:STEADY_SHOWN]


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
    slips = cached(("ideas", chosen["date"], chosen["book"], chosen["model"], style, game, tuple(table.index)), search,
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
        raise NotFound("These selections are no longer on the board. Refresh the board and select them again.")
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
