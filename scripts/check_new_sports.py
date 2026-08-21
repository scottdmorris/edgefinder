"""CLI sanity check for soccer and UFC data paths."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder import pipeline_soccer
from edgefinder.data import odds_api


def main() -> None:
    try:
        board, trained = pipeline_soccer.build_soccer_board("EPL")
        print(f"EPL: trained on {trained} matches, {len(board)} upcoming with lines")
        for m in board[:5]:
            best = m.get("best_ev")
            best_txt = "n/a" if best is None else f"{best * 100:+.1f}%"
            print(
                f"  {m['home']} v {m['away']} | "
                f"H/D/A {m['p_home']:.2f}/{m['p_draw']:.2f}/{m['p_away']:.2f} "
                f"| FD {m.get('home_ml')}/{m.get('draw_ml')}/{m.get('away_ml')} "
                f"| best EV {best_txt}{' | SUSPECT' if m.get('suspect') else ''}"
            )
    except Exception as exc:
        print(f"EPL failed: {exc}")

    try:
        fights = odds_api.fanduel_ufc()
        print(f"\nUFC: {len(fights)} events with FanDuel lines")
        for f in fights[:5]:
            print(f"  {f['home']} vs {f['away']} | {f['home_ml']}/{f['away_ml']} "
                  f"| {f['commence_time']}")
    except Exception as exc:
        print(f"UFC failed: {exc}")

    quota = odds_api.get_quota()
    print(f"\nquota: {quota}")


if __name__ == "__main__":
    main()
