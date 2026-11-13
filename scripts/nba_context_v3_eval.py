"""Does training on the absences the injury report would have shown beat context-v2?

context-v2 was trained with every recent-roster player missing from the box score counted
as out. Live, the model is fed the injury report, which lists about a third as many. This
script measures what that mismatch costs and whether training on the matching definition
(`known_only`, see models/nba_context.py) fixes it.

There is no archive of past injury reports, so "what live looks like" is stood in for by the
known-only numbers worked out from the box scores. Protocol as in the other scripts: choose
on 2024-25 (train 2023-24), score 2025-26 once (train 2023-24 + 2024-25), rotation players.

  v2_backtest   trained on the old numbers, tested on the old numbers (the published figure)
  v2_served     trained on the old numbers, tested on the known-only numbers (what runs live)
  v3            trained and tested on the known-only numbers
  no_absences   the same model with no absence inputs at all

Result (2025-26): v2_served 5.0887 against v2_backtest 5.0898, so the mismatch costs nothing
measurable; v3 5.1138, worse than v2_served by 0.025 (interval 0.017 to 0.034). Not adopted.
More history: 5 seasons instead of 2 improves the error by about 0.006, at the edge of what
can be told from zero. Not adopted either.

--history also asks whether more seasons of training data help: v3 trained on the 1 to 5
seasons before the scored one.

Usage:  python scripts/nba_context_v3_eval.py [--history]
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import nba_stats  # noqa: E402
from edgefinder.models import nba_context, nba_features, nba_minutes  # noqa: E402
from edgefinder.models.nba_shot_features import SHOT_COLUMNS, add_shot_features  # noqa: E402

import nba_context_eval as base  # noqa: E402  (same folder: reuse the exact setup)

ABSENCES = nba_context.ABSENCE_COLUMNS
DIRECT = base.DIRECT_CONTEXT + SHOT_COLUMNS
NEEDED = ["min_ewma_mid", "rate_ewma_05"]
METHODS = ["v2_backtest", "v2_served", "v3", "no_absences"]
HISTORY_SEASONS = ("2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25",
                   "2025-26")


def build(games: pd.DataFrame, known_only: bool) -> pd.DataFrame:
    features = nba_context.add_context(nba_features.build_features(games), games, known_only)
    return add_shot_features(features)


def blend(train: pd.DataFrame, test: pd.DataFrame, absences: bool = True) -> np.ndarray:
    """context-v2's recipe: the direct model with shot inputs averaged with minutes x rate."""
    direct_columns = DIRECT if absences else [c for c in DIRECT if c not in ABSENCES]
    minutes_columns = nba_minutes.MINUTES_FEATURES + (ABSENCES if absences else [])
    model, kept = base.fit_direct(train, direct_columns)
    direct = np.clip(model.predict(test[kept]), 0.05, None)
    minutes = nba_minutes.MinutesModel(features=minutes_columns).fit(train)
    return (direct + nba_minutes.project_points(test, minutes.predict(test))) / 2.0


def pool(frame: pd.DataFrame, seasons) -> pd.DataFrame:
    seasons = (seasons,) if isinstance(seasons, str) else seasons
    return frame[frame["season"].isin(seasons)]


def score(old: pd.DataFrame, known: pd.DataFrame, train_seasons, test_season: str) -> pd.DataFrame:
    """Every variant's prediction for the test season's rotation players. `old` and `known`
    hold the same rows in the same order; only the absence columns differ."""
    test_old = base.rotation(pool(old, test_season)).dropna(subset=NEEDED)
    test_known = known.loc[test_old.index]
    out = test_known.copy()
    out["v2_backtest"] = blend(pool(old, train_seasons), test_old)
    out["v2_served"] = blend(pool(old, train_seasons), test_known)
    out["v3"] = blend(pool(known, train_seasons), test_known)
    out["no_absences"] = blend(pool(known, train_seasons), test_known, absences=False)
    return out


def show(title: str, scored: pd.DataFrame) -> None:
    print(title)
    for method in METHODS:
        print(f"  {method:12s} MAE {base.mae(scored, method):.4f}")
    for challenger, champion in (("v3", "v2_served"), ("v3", "no_absences"),
                                 ("v2_backtest", "v2_served")):
        gain, low, high = base.paired_ci(scored, challenger, champion)
        verdict = "real" if low > 0 else "worse" if high < 0 else "not distinguishable from zero"
        print(f"  {challenger} over {champion}: {gain:+.4f}  [{low:+.4f}, {high:+.4f}]  {verdict}")
    out = scored[scored["lost_min"] > 0]
    print(f"  where a teammate was known to be out (n={len(out):,} of {len(scored):,}):")
    for method in METHODS:
        print(f"    {method:12s} MAE {base.mae(out, method):.4f}")
    print()


def history(today: dt.date) -> None:
    games = pd.concat([nba_stats.load_season(s, today=today) for s in HISTORY_SEASONS],
                      ignore_index=True)
    known = build(games, known_only=True)
    for test_season, label in ((base.VALIDATE, "choose"), (base.TEST, "confirm")):
        position = HISTORY_SEASONS.index(test_season)
        test = base.rotation(pool(known, test_season)).dropna(subset=NEEDED)
        print(f"More history ({label}): v3 scored on {test_season}, by seasons trained on")
        results = test[["player_id", "pts"]].copy()
        for count in (1, 2, 3, 4, 5):
            seasons = HISTORY_SEASONS[position - count:position]
            results[f"n{count}"] = blend(pool(known, seasons), test)
            print(f"  {count} season(s) ({seasons[0]} on)  MAE {base.mae(results, f'n{count}'):.4f}")
        for count in (3, 5):
            gain, low, high = base.paired_ci(results, f"n{count}", "n2")
            print(f"  {count} seasons over 2: {gain:+.4f}  [{low:+.4f}, {high:+.4f}]")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    today = dt.date.today()
    if args.history:
        history(today)
        return
    games = pd.concat([nba_stats.load_season(s, today=today) for s in base.SEASONS],
                      ignore_index=True)
    old, known = build(games, known_only=False), build(games, known_only=True)
    assert (old["game_id"].to_numpy() == known["game_id"].to_numpy()).all()
    rows = base.rotation(old)
    print(f"Minutes lost per player-game: old definition {rows['lost_min'].mean():.1f}, "
          f"known only {known.loc[rows.index, 'lost_min'].mean():.1f}\n")
    show(f"Step 1: {base.VALIDATE} (train {', '.join(base.SELECT_TRAIN)})",
         score(old, known, base.SELECT_TRAIN, base.VALIDATE))
    show(f"Step 2: {base.TEST}, scored once (train {', '.join(base.FINAL_TRAIN)})",
         score(old, known, base.FINAL_TRAIN, base.TEST))


if __name__ == "__main__":
    main()
