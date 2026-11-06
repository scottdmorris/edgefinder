"""Where FanDuel and Kalshi disagree about the same bet.

Two markets price many of the same player-points bets: FanDuel (a sportsbook) and Kalshi (an
exchange, where the price is set by people trading against each other). When one prices a bet
well above the other's own fair chance, one of them is probably wrong, and betting the generous
one is worth a look. This is the "beat the bookies with their own numbers" idea: it needs no
model of our own, only the other market as a reference.

How a gap is measured: take the reference market's fair chance (its price with the margin
removed), multiply by the decimal odds offered at the other book, and subtract 1. That is the
expected profit per $1 IF the reference is right. Positive means the offering book pays more
than the reference thinks the bet is worth.

Two ways to line bets up:
- exact: the same player, game and number on both (FanDuel's "25+" ladder and Kalshi's "25+"
  contracts line up exactly; FanDuel's main over/under rarely sits on a Kalshi number).
- estimated: FanDuel's main line priced from a curve fitted to that player's Kalshi ladder, so
  "Over 27.5" can be compared even though Kalshi only lists 25+ and 30+. Labelled as estimated.

Caveats that matter: Kalshi prices are before its trading fees; only liquid Kalshi markets are
ever recorded, but they can still be thin; and both prices are the ones recorded at the same
snapshot, which may have moved since.
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from ..betting import negbin
from ..betting.odds_math import american_to_decimal, implied_prob
from ..models import nba_context_v2

MIN_EDGE = 0.03            # expected profit per $1 needed to flag a gap
MAX_EDGE = 0.30            # bigger than this is almost always a stale or broken price
SAME_SNAPSHOT_MINUTES = 45
MIN_LADDER = 2             # Kalshi lines needed before a curve is fitted to them
COLUMNS = ["Game", "Player", "player_id", "event_id", "Bet", "Side", "line", "Book", "Odds",
           "Price says %", "Reference %", "Reference", "How", "Edge %"]
BOOK_NAMES = {"fanduel": "FanDuel", "kalshi": "Kalshi"}


def _edge(reference_p: float, american: float) -> float:
    return reference_p * american_to_decimal(american) - 1.0


def _first(rows: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """One row per bet: every model writes the same prices, so keep the earliest."""
    return rows.sort_values("recorded_at").drop_duplicates(keys)


def _close_in_time(a: str, b: str) -> bool:
    gap = abs(pd.Timestamp(a) - pd.Timestamp(b))
    return gap <= pd.Timedelta(minutes=SAME_SNAPSHOT_MINUTES)


def fit_ladder_mean(points: list[tuple[float, float]]) -> float | None:
    """The projected points that best explain a Kalshi ladder: [(line, fair chance of the over)].
    Uses the same projection-dependent spread as context-v2. None with fewer than MIN_LADDER."""
    if len(points) < MIN_LADDER:
        return None
    lines = np.array([p[0] for p in points])
    chances = np.array([p[1] for p in points])

    def misfit(mean: float) -> float:
        fitted = np.array([negbin.over_prob(line, mean, nba_context_v2.MODEL_DISPERSION)
                           for line in lines])
        return float(np.sum((fitted - chances) ** 2))

    return float(minimize_scalar(misfit, bounds=(0.5, 70.0), method="bounded").x)


def _row(game, player, pid, event, bet, side, line, book, odds, reference_p, reference, how):
    edge = _edge(reference_p, odds)
    return {"Game": game, "Player": player, "player_id": pid, "event_id": event, "Bet": bet,
            "Side": side, "line": line, "Book": book, "Odds": odds,
            "Price says %": implied_prob(odds) * 100.0, "Reference %": reference_p * 100.0,
            "Reference": reference, "How": how, "Edge %": edge * 100.0}


def find_gaps(ledger: pd.DataFrame, alt_ledger: pd.DataFrame, game_date: str,
              min_edge: float = MIN_EDGE) -> pd.DataFrame:
    """Every bet on `game_date` that one market prices well above the other's fair chance,
    biggest gap first. Points only: FanDuel's other stats are not recorded."""
    day = ledger[(ledger["game_date"] == game_date) & (ledger["stat"].fillna("points") == "points")]
    books = day["book"].fillna("fanduel")
    fd = _first(day[books == "fanduel"], ["event_id", "player_id", "line"])
    ks = _first(day[books == "kalshi"], ["event_id", "player_id", "line"])
    if ks.empty:                    # Kalshi is in every comparison; FanDuel's X+ needs no main line
        return pd.DataFrame(columns=COLUMNS)
    rows = []
    kalshi_by = {(r.event_id, int(r.player_id), float(r.line)): r for r in ks.itertuples()}

    # FanDuel's main over/under against Kalshi: exact when the number matches, estimated otherwise
    ladders = {key: [(float(r.line), float(r.fair_p_over)) for r in group.itertuples()]
               for key, group in ks.groupby(["event_id", "player_id"])}
    for r in fd.itertuples():
        game = f"{r.away} @ {r.home}"
        exact = kalshi_by.get((r.event_id, int(r.player_id), float(r.line)))
        if exact is not None and _close_in_time(r.recorded_at, exact.recorded_at):
            reference_over, how = float(exact.fair_p_over), "exact"
            # and the other way: Kalshi's contracts against FanDuel's own fair chance
            for side, odds, p in (("Over", exact.over_odds, r.fair_p_over),
                                  ("Under", exact.under_odds, 1 - r.fair_p_over)):
                rows.append(_row(game, r.player, int(r.player_id), r.event_id,
                                 f"{side} {r.line:g}", side, float(r.line), "kalshi", float(odds),
                                 float(p), "FanDuel", "exact"))
        else:
            ladder = ladders.get((r.event_id, r.player_id), [])
            mean = fit_ladder_mean(ladder)
            if mean is None:
                continue
            reference_over = float(negbin.over_prob(float(r.line), mean,
                                                    nba_context_v2.MODEL_DISPERSION))
            how = "estimated"
        for side, odds, p in (("Over", r.over_odds, reference_over),
                              ("Under", r.under_odds, 1 - reference_over)):
            if pd.notna(odds):
                rows.append(_row(game, r.player, int(r.player_id), r.event_id,
                                 f"{side} {r.line:g}", side, float(r.line), "fanduel",
                                 float(odds), p, "Kalshi", how))

    # FanDuel's "X+" ladder against Kalshi's contracts on the same number
    if not alt_ledger.empty:
        alts = alt_ledger[alt_ledger["game_date"] == game_date]
        alts = _first(alts, ["event_id", "player_id", "threshold"])
        for r in alts.itertuples():
            line = float(r.threshold) - 0.5
            exact = kalshi_by.get((r.event_id, int(r.player_id), line))
            if exact is None or not _close_in_time(r.recorded_at, exact.recorded_at):
                continue
            rows.append(_row(f"{r.away} @ {r.home}", r.player, int(r.player_id), r.event_id,
                             f"{int(r.threshold)}+", f"{int(r.threshold)}+", line, "fanduel",
                             float(r.over_odds), float(exact.fair_p_over), "Kalshi", "exact"))

    table = pd.DataFrame(rows, columns=COLUMNS)
    if table.empty:
        return table
    keep = (table["Edge %"] >= min_edge * 100.0) & (table["Edge %"] <= MAX_EDGE * 100.0)
    return table[keep].sort_values("Edge %", ascending=False).reset_index(drop=True)


def describe(row) -> str:
    """'FanDuel pays +150 (40% implied); Kalshi's fair chance is 46%.'"""
    book = BOOK_NAMES.get(row["Book"], row["Book"])
    odds = row["Odds"]
    price = f"+{odds:.0f}" if odds > 0 else f"{odds:.0f}"
    estimated = " (estimated from its ladder)" if row["How"] == "estimated" else ""
    return (f"{book} pays {price} ({row['Price says %']:.0f}% implied); "
            f"{row['Reference']}'s fair chance is {row['Reference %']:.0f}%{estimated}.")


def candidate_index(candidates: pd.DataFrame, row) -> int | None:
    """Where this gap's bet sits in the Parlay builder's table, so it can be added to a slip."""
    match = candidates[(candidates["player_id"] == row["player_id"])
                       & (candidates["event_id"] == row["event_id"])
                       & (candidates["Side"] == row["Side"])
                       & np.isclose(candidates["line"].astype(float), float(row["line"]))]
    return None if match.empty else int(match.index[0])


__all__ = ["find_gaps", "fit_ladder_mean", "describe", "candidate_index", "MIN_EDGE",
           "MAX_EDGE", "COLUMNS"]
