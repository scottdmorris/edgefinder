"""Where FanDuel and a second sportsbook disagree about the same player.

Two books pricing the same bet rarely agree exactly. When FanDuel pays more than the other
book's own fair chance says the bet is worth, or posts a different number altogether, one of
them is off. This needs no model: the other book is the reference.

On the same number, the edge is FanDuel's payout times the other book's fair chance (its
price with the margin removed), minus 1: the expected profit per $1 IF the other book is
right. Two books with identical prices show a small negative edge, which is just the margin.
On different numbers no edge is worked out; the difference in the number is the signal.
"""

import numpy as np
import pandas as pd

from ..betting.odds_math import american_to_decimal, devig_two_way, implied_prob

MIN_EDGE = 0.03            # expected profit per $1 worth pointing out
MIN_LINE_DIFF = 1.0        # a number this far apart is worth pointing out
COLUMNS = ["player", "fanduel_line", "other_line", "line_diff", "other_fair_over",
           "over_edge", "under_edge"]


def _fair_over(line: dict) -> float:
    """The book's chance of the over with its margin removed, or NaN if a side is missing."""
    over, under = line.get("over_odds"), line.get("under_odds")
    if pd.isna(over) or pd.isna(under):
        return np.nan
    return devig_two_way(implied_prob(over), implied_prob(under))[0]


def _edge(chance: float, american) -> float:
    if pd.isna(chance) or pd.isna(american):
        return np.nan
    return chance * american_to_decimal(american) - 1.0


def compare(fanduel_lines: list[dict], other_lines: list[dict]) -> pd.DataFrame:
    """One row per player both books list. Lines are {"player", "line", "over_odds",
    "under_odds"}; a player listed twice by a book keeps his first line."""
    other_by_player: dict[str, dict] = {}
    for line in other_lines:
        other_by_player.setdefault(line["player"], line)
    rows, seen = [], set()
    for line in fanduel_lines:
        other = other_by_player.get(line["player"])
        if other is None or line["player"] in seen:
            continue
        seen.add(line["player"])
        same_number = float(line["line"]) == float(other["line"])
        fair_over = _fair_over(other)
        rows.append({
            "player": line["player"], "fanduel_line": float(line["line"]),
            "other_line": float(other["line"]),
            "line_diff": float(line["line"]) - float(other["line"]),
            "other_fair_over": fair_over,
            "over_edge": _edge(fair_over, line.get("over_odds")) if same_number else np.nan,
            "under_edge": _edge(1.0 - fair_over, line.get("under_odds")) if same_number else np.nan,
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def worth_a_look(table: pd.DataFrame, min_edge: float = MIN_EDGE,
                 min_line_diff: float = MIN_LINE_DIFF) -> pd.DataFrame:
    """The rows where FanDuel pays at least `min_edge` over the other book's fair chance, or
    the two books' numbers are at least `min_line_diff` apart."""
    best = table[["over_edge", "under_edge"]].max(axis=1)
    return table[(best >= min_edge) | (table["line_diff"].abs() >= min_line_diff)]
