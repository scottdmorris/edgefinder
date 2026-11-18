"""Do slips with many legs pay? One slip a night from 2025-26 Kalshi player-points markets.

Reads the rows the season backtest saved (data/kalshi_history/backtest_rows.csv, written by
nba_kalshi_backtest.py) and builds, each night, a slip of the likeliest markets by the same
30/70 blend the app uses, one player each and at most `per_game` a game, from the night's eight
busiest games (the snapshot budget). Each slip is priced two ways:

- Kalshi: the product of the asks, plus Kalshi's fee on each leg (prices you could pay).
- Sportsbook-style: the midpoint with a 4.5% margin per leg (a -110/-110 book's cut).

Run: python scripts/nba_many_leg_backtest.py [--max-spread 0.04]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from edgefinder.data import kalshi_history as kh  # noqa: E402
from edgefinder.tracking.nba_paper import MODEL_WEIGHT  # noqa: E402

ROWS = ROOT / "data" / "kalshi_history" / "backtest_rows.csv"
MODEL = "p_Smarter corrected"
BOOK_MARGIN = 1.045
GAMES_A_NIGHT = 8
BOOTSTRAP = 2000


def load(max_spread: float) -> pd.DataFrame:
    rows = pd.read_csv(ROWS)
    rows = rows[(rows["stat"] == "points")].dropna(subset=["yes_ask", "yes_bid", "mid", MODEL])
    rows = rows[(rows["yes_ask"] > 0) & (rows["yes_ask"] < 1)
                & (rows["yes_ask"] - rows["yes_bid"] <= max_spread)]
    return rows.assign(blend=MODEL_WEIGHT * rows[MODEL] + (1 - MODEL_WEIGHT) * rows["mid"])


def night_slip(night: pd.DataFrame, legs: int, per_game: int) -> pd.DataFrame:
    night = night.sort_values("blend", ascending=False).drop_duplicates("player_id")
    busiest = night.groupby("game_id")["total_volume"].sum().nlargest(GAMES_A_NIGHT).index
    night = night[night["game_id"].isin(busiest)]
    return night[night.groupby("game_id").cumcount() < per_game].head(legs)


def run(rows: pd.DataFrame, legs: int, per_game: int, rng) -> dict | None:
    kalshi, book, won, pays = [], [], [], []
    for _, night in rows.groupby("game_date"):
        slip = night_slip(night, legs, per_game)
        if len(slip) < legs:
            continue
        ask, mid = slip["yes_ask"].to_numpy(), slip["mid"].to_numpy()
        hit = bool((slip["hit"] == 1).all())
        decimal = float(np.prod(1 / (mid * BOOK_MARGIN)))
        kalshi.append((1 / np.prod(ask) - 1 if hit else -1.0) - float(np.sum(kh.taker_fee(ask) / ask)))
        book.append(decimal - 1 if hit else -1.0)
        won.append(hit)
        pays.append(decimal)
    if not won:
        return None
    units = np.array(kalshi)
    draws = [units[rng.integers(0, len(units), len(units))].mean() for _ in range(BOOTSTRAP)]
    low, high = np.percentile(draws, [2.5, 97.5])
    return {"Legs": legs, "A game": per_game, "Nights": len(won), "Won": f"{np.mean(won):.0%}",
            "Typical payout": f"+{(np.median(pays) - 1) * 100:.0f}",
            "Return at Kalshi prices": f"{units.mean():+.0%}", "95% interval": f"{low:+.0%} to {high:+.0%}",
            "Return, sportsbook-style": f"{np.mean(book):+.0%}"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-spread", type=float, default=1.0,
                        help="leave out markets whose ask is more than this above the bid")
    args = parser.parse_args()
    rows, rng = load(args.max_spread), np.random.default_rng(7)
    table = [r for legs, per_game in [(2, 1), (3, 1), (4, 1), (6, 1), (8, 1), (8, 2), (10, 2)]
             if (r := run(rows, legs, per_game, rng))]
    header = list(table[0])
    print("| " + " | ".join(header) + " |\n|" + "---:|" * len(header))
    for row in table:
        print("| " + " | ".join(str(row[key]) for key in header) + " |")


if __name__ == "__main__":
    main()
