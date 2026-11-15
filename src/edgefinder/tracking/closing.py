"""The fair (no-vig) closing price, and how a bet compares with it.

A book's closing price includes its cut, so beating it can still lose money. Removing the cut
from each book's last price before tip-off, and averaging the books that closed on the same
number, gives the market's best fair estimate of each side. A bet's closing-line value is its
payout times that fair chance, minus 1: positive means the price taken beat where the market
finished. Over many bets this predicts profit far sooner than wins and losses do.
"""

import math

import pandas as pd

from ..betting.odds_math import american_to_decimal, devig_two_way, implied_prob

Key = tuple[str, str, str, float]     # (event_id, player, stat, line)
DEFAULT_STAT = "points"               # the sportsbook snapshots are all points lines


def _last_late(snapshots: pd.DataFrame | None) -> pd.DataFrame:
    if snapshots is None or snapshots.empty:
        return pd.DataFrame()
    late = snapshots[snapshots["phase"] == "late"] if "phase" in snapshots.columns else snapshots
    # a sportsbook lists one number per player, so its close is its last one; Kalshi lists a
    # ladder, so each rung of each stat has its own close
    ladder = "stat" in late.columns
    keys = ["event_id", "player", "stat", "line"] if ladder else ["event_id", "player"]
    return late.sort_values("fetched_at").groupby(keys).tail(1)


def fair_closes(*sources: pd.DataFrame | None) -> dict[Key, float]:
    """{(event_id, player, stat, line): the average fair chance of the over} across the sources
    (each a snapshot table with phase, fetched_at, event_id, player, line and both prices),
    using each source's last late price. A book that closed on another number does not count
    for this one."""
    found: dict[Key, list[float]] = {}
    for source in sources:
        for row in _last_late(source).itertuples():
            if pd.isna(row.over_odds) or pd.isna(row.under_odds):
                continue
            fair_over = devig_two_way(implied_prob(row.over_odds), implied_prob(row.under_odds))[0]
            stat = getattr(row, "stat", DEFAULT_STAT)
            key = (str(row.event_id), str(row.player), str(stat), float(row.line))
            found.setdefault(key, []).append(fair_over)
    return {key: sum(values) / len(values) for key, values in found.items()}


def novig_clv_pct(is_over: bool, american, fair_over: float) -> float:
    """The bet's payout times the fair closing chance of its side, minus 1, as a percent."""
    if fair_over is None or pd.isna(fair_over) or american is None or pd.isna(american):
        return math.nan
    chance = fair_over if is_over else 1.0 - fair_over
    return (american_to_decimal(float(american)) * chance - 1.0) * 100.0
