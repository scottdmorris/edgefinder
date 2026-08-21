"""CLI sanity check: build a slate's board with live odds and show the
suggester's output. Usage: python scripts/check_board.py [YYYY-MM-DD]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder import pipeline
from edgefinder.betting import suggest


def main() -> None:
    date_iso = sys.argv[1] if len(sys.argv) > 1 else "2026-07-19"
    board = pipeline.build_board(2026, date_iso)
    with_odds = [g for g in board if g.get("home_ml") is not None]
    print(f"games: {len(board)} | with FanDuel odds: {len(with_odds)}")
    for g in with_odds:
        print(
            f"{g['away']} @ {g['home']} | p_home={g['p_home']:.3f} "
            f"| FD ml {g['away_ml']}/{g['home_ml']} "
            f"| total {g.get('total_line')} "
            f"| best EV {g['best_ev'] * 100:+.1f}%"
        )
    legs = suggest.board_candidate_legs(board)
    combos = suggest.suggest_parlays(legs, num_legs=2)
    print(f"\nsuggested +EV 2-leg parlays: {len(combos)}")
    for c in combos:
        names = " + ".join(l.description for l in c.legs)
        print(f"  {names} | hits {c.true_prob * 100:.1f}% | EV {c.ev * 100:+.1f}%")


if __name__ == "__main__":
    main()
