"""How much do players' points in the same game move together?

A parlay with two legs from one game is not two independent bets: a fast
game lifts everyone, a blowout cuts starters' minutes, and teammates
compete for shots. This measures it from history instead of assuming it.

Method: for each player-game, standardise the miss (actual points minus the
rolling-average prediction) by the negative-binomial spread implied by that
prediction. The correlation of those standardised misses across pairs of
players in the same game is the same-game correlation, reported separately
for teammates and for opponents. Only players projected for real minutes
count, since bench players' points are mostly noise.
"""

import numpy as np
import pandas as pd

MIN_PROJECTED_POINTS = 10.0
MIN_PRIOR_GAMES = 10


def standardised_misses(games: pd.DataFrame, dispersion: float, stat: str = "pts",
                        min_projection: float = MIN_PROJECTED_POINTS) -> pd.DataFrame:
    """Rows with a z column: (stat - pred_ewma) / sd. `games` needs the
    columns add_baseline_predictions produces for that stat, plus game_id and
    team. `min_projection` keeps out players too small for the stat to be
    anything but noise (10 for points; use a lower bar for rebounds or
    assists)."""
    rated = games[(games["pred_ewma"] >= min_projection)
                  & (games["n_prior"] >= MIN_PRIOR_GAMES)].copy()
    variance = rated["pred_ewma"] + rated["pred_ewma"] ** 2 / dispersion
    rated["z"] = (rated[stat] - rated["pred_ewma"]) / np.sqrt(variance)
    return rated[["game_id", "team", "z"]]


def pair_correlations(misses: pd.DataFrame) -> dict[str, float]:
    """Average correlation of standardised misses across teammate pairs
    and across opposing pairs, plus how many pairs each rests on."""
    scale = float(np.mean(misses["z"] ** 2))
    by_team = misses.groupby(["game_id", "team"])["z"].agg(
        total="sum", squares=lambda s: float((s ** 2).sum()), count="size").reset_index()

    teammate_sum = float(((by_team["total"] ** 2 - by_team["squares"]) / 2.0).sum())
    teammate_pairs = float((by_team["count"] * (by_team["count"] - 1) / 2.0).sum())

    opponent_sum = opponent_pairs = 0.0
    for _, game in by_team.groupby("game_id"):
        if len(game) != 2:
            continue
        a, b = game.iloc[0], game.iloc[1]
        opponent_sum += float(a["total"] * b["total"])
        opponent_pairs += float(a["count"] * b["count"])

    return {
        "teammate": teammate_sum / teammate_pairs / scale if teammate_pairs else 0.0,
        "opponent": opponent_sum / opponent_pairs / scale if opponent_pairs else 0.0,
        "teammate_pairs": int(teammate_pairs),
        "opponent_pairs": int(opponent_pairs),
    }
