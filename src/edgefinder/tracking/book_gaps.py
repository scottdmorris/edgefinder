"""Where FanDuel and a second sportsbook disagree about the same player.

Two books pricing the same bet rarely agree exactly. When FanDuel pays more than the other
book's own fair chance says the bet is worth, or posts a different number altogether, one of
them is off. This needs no model: the other book is the reference.

On the same number, the edge is FanDuel's payout times the other book's fair chance (its
price with the margin removed), minus 1: the expected profit per $1 IF the other book is
right. Two books with identical prices show a small negative edge, which is just the margin.
On different numbers no edge is worked out; the difference in the number is the signal.
"""

from pathlib import Path

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


# ---- the gaps as bets, graded like the Kalshi ones (tracking/gap_log) -----------------------------

LOG_PATH = Path(__file__).resolve().parents[3] / "data" / "book_gap_log.csv"
HOW = ("price", "number")          # a better price on the same number, or a different number


def _bet(row: pd.Series, fanduel: dict) -> tuple[str, float, float, float] | None:
    """(side, FanDuel odds, DraftKings' fair chance of that side, edge %) for a gap worth
    betting at FanDuel, or None. A different number is bet on the side it makes easier."""
    if row["line_diff"] != 0:
        side = "Over" if row["line_diff"] < 0 else "Under"
        odds = fanduel["over_odds"] if side == "Over" else fanduel["under_odds"]
        fair = row["other_fair_over"] if side == "Over" else 1.0 - row["other_fair_over"]
        return (side, odds, fair, np.nan) if pd.notna(odds) else None
    over, under = row["over_edge"], row["under_edge"]
    if pd.isna(over) and pd.isna(under):
        return None
    if pd.isna(under) or (pd.notna(over) and over >= under):
        return "Over", fanduel["over_odds"], row["other_fair_over"], over * 100.0
    return "Under", fanduel["under_odds"], 1.0 - row["other_fair_over"], under * 100.0


def rows_to_log(event: dict, fanduel_lines: list[dict], other_lines: list[dict],
                player_ids: dict[str, int], now, game_date: str,
                reference: str = "DraftKings") -> list[dict]:
    """The gaps worth a look, as FanDuel bets in tracking/gap_log's format. Nothing is logged
    once the game has started, or for a player the ledger cannot identify."""
    if pd.Timestamp(event["commence_time"]) <= pd.Timestamp(now):
        return []
    fanduel = {line["player"]: line for line in fanduel_lines}
    rows = []
    for _, gap in worth_a_look(compare(fanduel_lines, other_lines)).iterrows():
        player = gap["player"]
        bet = _bet(gap, fanduel[player])
        if bet is None or player not in player_ids:
            continue
        side, odds, fair, edge = bet
        rows.append({
            "logged_at": now.isoformat(), "game_date": game_date, "event_id": event["event_id"],
            "commence_time": event["commence_time"], "game": f"{event['away']} @ {event['home']}",
            "player": player, "player_id": int(player_ids[player]),
            "bet": f"{side} {gap['fanduel_line']:g}", "side": side, "line": gap["fanduel_line"],
            "book": "fanduel", "odds": float(odds), "price_p": round(implied_prob(odds), 6),
            "reference": reference,
            "reference_p": round(float(fair), 6) if pd.notna(fair) else None,
            "how": "number" if gap["line_diff"] != 0 else "price",
            "edge_pct": round(float(edge), 4) if pd.notna(edge) else None,
            "status": "pending", "actual": None, "result": None, "pnl_units": None,
            "clv_novig_pct": None})
    return rows
