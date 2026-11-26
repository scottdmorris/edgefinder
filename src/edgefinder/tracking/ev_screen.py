"""Lines one book prices better than the rest of the market says they are worth.

PropLine returns about 30 books' main player lines in the one request a run already makes.
For each player, stat and number, every book that lists both sides has its margin removed
(proportional devig), and the other books' fair chances are averaged into a market fair
chance. A book whose payout on one side, times that fair chance, beats 1 by at least
`MIN_EDGE` is flagged: its price is better than the market's consensus says the bet is worth.

The flagged book is always left out of its own fair price, so one stale book can't vouch for
itself, and a book whose fair chance is far from the median of the rest (`OUTLIER`) is left out
of everyone's fair price, so one stale book can't move the market for the others. Pick'em apps are left out altogether: their "prices" are fixed payouts (PrizePicks and
Pick6 list every line at +100), not two-way markets. Prediction markets list several numbers
per player; each number is compared only with books on that same number.

Every book counts the same for now (`WEIGHTS` is empty). Sharp books such as Pinnacle are
usually weighted more, but nothing here has graded the books yet, so a weighting would be a
guess; the paper ledger (tracking/ev_log) is what will show whether one is warranted.

This is a paper experiment. It says where prices disagree, not what to bet.
"""

import math

import pandas as pd

from ..betting.odds_math import american_to_decimal, devig_two_way, implied_prob, prob_to_american
from . import closing

MIN_EDGE = 0.03          # expected profit per $1 at the fair price, worth flagging
MAX_EDGE = 0.25          # past this the price is far likelier stale or misread than a gift
MIN_BOOKS = 3            # other books, both sides on the same number, behind a fair price
OUTLIER = 0.15           # a book this far from the line's median fair chance is left out of fair
FAIR_RANGE = (0.2, 0.8)  # fair chance of the side; the far tails are where devig is weakest
PICKEM = frozenset({"prizepicks", "pick6", "underdog", "sleeper", "dabble", "parlayplay"})
WEIGHTS: dict[str, float] = {}      # book -> weight in the fair price; missing books count 1
GROUP = ["event_id", "stat", "player", "line"]
COLUMNS = ["event_id", "commence_time", "game", "stat", "player", "player_id", "line", "book",
           "side", "odds", "fair_p", "fair_odds", "edge_pct", "books"]
BOOK_NAMES = {
    "fanduel": "FanDuel", "draftkings": "DraftKings", "betmgm": "BetMGM", "betrivers": "BetRivers",
    "fanatics": "Fanatics", "hardrock": "Hard Rock", "pinnacle": "Pinnacle", "novig": "Novig",
    "prophetx": "ProphetX", "kalshi": "Kalshi", "polymarket_us": "Polymarket",
    "thescorebet": "theScore", "unibet": "Unibet", "fliff": "Fliff", "rebet": "Rebet",
    "courtside": "Courtside", "tonybet": "TonyBet", "stoiximan": "Stoiximan",
    "sportzino": "Sportzino", "elabet": "Elabet", "dst_propbuilder": "DST PropBuilder",
}


def book_name(book: str) -> str:
    return BOOK_NAMES.get(book, str(book).replace("_", " ").title())


def latest(snapshots: pd.DataFrame | None, now=None) -> pd.DataFrame:
    """Each game's most recent PropLine fetch, without pick'em apps. With `now`, only games
    that have not started (a price fetched before tip is no use once the game is on)."""
    if snapshots is None or snapshots.empty:
        return pd.DataFrame()
    table = closing.before_tip(snapshots)
    table = table[~table["book"].isin(PICKEM)]
    if now is not None:
        tips = pd.to_datetime(table["commence_time"], utc=True, errors="coerce")
        table = table[tips > pd.Timestamp(now)]
    if table.empty:
        return table
    newest = table.groupby("event_id")["fetched_at"].transform("max")
    return table[table["fetched_at"] == newest].reset_index(drop=True)


def _fair_over(over, under) -> float:
    if pd.isna(over) or pd.isna(under):
        return math.nan
    return devig_two_way(implied_prob(float(over)), implied_prob(float(under)))[0]


def _consensus(others: pd.DataFrame, weights: dict[str, float]) -> float:
    w = others["book"].map(lambda b: weights.get(b, 1.0)).astype(float)
    return float((others["fair_over"] * w).sum() / w.sum()) if w.sum() > 0 else math.nan


def _flags_for(group: pd.DataFrame, min_edge: float, max_edge: float, min_books: int,
               weights: dict[str, float]) -> list[dict]:
    two_sided = group[group["fair_over"].notna()]
    two_sided = two_sided[(two_sided["fair_over"] - two_sided["fair_over"].median()).abs() <= OUTLIER]
    out = []
    for row in group.itertuples(index=False):
        others = two_sided[two_sided["book"] != row.book]
        if len(others) < min_books:
            continue
        fair_over = _consensus(others, weights)
        for side, odds, fair in (("Over", row.over_odds, fair_over),
                                 ("Under", row.under_odds, 1.0 - fair_over)):
            if pd.isna(odds) or pd.isna(fair) or not FAIR_RANGE[0] <= fair <= FAIR_RANGE[1]:
                continue
            edge = american_to_decimal(float(odds)) * fair - 1.0
            if min_edge <= edge <= max_edge:
                out.append({
                    "event_id": row.event_id, "commence_time": row.commence_time,
                    "game": f"{row.away} @ {row.home}", "stat": row.stat, "player": row.player,
                    "player_id": row.player_id, "line": float(row.line), "book": row.book,
                    "side": side, "odds": float(odds), "fair_p": round(fair, 6),
                    "fair_odds": round(prob_to_american(fair)), "edge_pct": round(edge * 100, 2),
                    "books": len(others)})
    return out


def screen(lines: pd.DataFrame, min_edge: float = MIN_EDGE, max_edge: float = MAX_EDGE,
           min_books: int = MIN_BOOKS, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Every side of every line priced at least `min_edge` better than the other books' fair
    chance, best edge first. `lines` is one fetch per game in PropLine's archive shape
    (event_id, commence_time, home, away, book, stat, player, player_id, line, both odds)."""
    if lines is None or lines.empty:
        return pd.DataFrame(columns=COLUMNS)
    table = lines[~lines["book"].isin(PICKEM)].copy()
    table["fair_over"] = [_fair_over(o, u) for o, u in zip(table["over_odds"], table["under_odds"])]
    weights = WEIGHTS if weights is None else weights
    rows = []
    for _, group in table.groupby(GROUP, sort=False):
        if group["book"].nunique() > min_books:          # a flag needs min_books others
            rows += _flags_for(group, min_edge, max_edge, min_books, weights)
    found = pd.DataFrame(rows, columns=COLUMNS)
    return found.sort_values(["edge_pct", "player"], ascending=[False, True]).reset_index(drop=True)
