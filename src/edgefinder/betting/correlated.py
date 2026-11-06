"""Parlays whose legs share a game.

Legs from different games are independent, so their probabilities multiply.
Legs from one game are priced with a Gaussian copula: each player's points
get a latent standard-normal score, and players in the same game are
correlated through it. The two correlations are measured from history by
`models.nba_correlation` (teammates are slightly negative, opponents
slightly positive; both are small).

An over or an X+ leg hits when the player's score is high, an under when it
is low. Flipping the sign of an over leg turns every leg into "score at or
below its threshold", and in both cases that threshold is the leg's own
probability pushed through the normal quantile function.
"""

from dataclasses import dataclass
from itertools import groupby

import numpy as np
from scipy import stats

from .ev import ev_per_unit
from .odds_math import american_to_decimal

# Measured on 2023-24 to 2025-26 game logs (about 60,000 teammate pairs and
# 70,000 opposing pairs per stat); see scripts/nba_correlation_report.py.
# (teammates, opponents) for two bets on the SAME stat in one game. Every one
# is small.
CORRELATIONS = {
    "points": (-0.026, 0.023),
    "rebounds": (-0.005, 0.023),
    "assists": (-0.025, 0.014),
    "threes": (-0.002, 0.004),
}
# Bets on DIFFERENT stats, measured the same way over 2023-24 to 2025-26 (see
# cross_report in scripts/nba_correlation_report.py), keyed by the two stats in
# alphabetical order: (the same player, teammates, opponents). Between different
# players they are close to nothing (a teammate's assists and another's points is
# the largest, +0.08). The same player's own stats are the exception: his points
# and threes move together almost lock-step, so a slip with both is far likelier
# to hit, or miss, together than the legs' separate prices suggest.
CROSS_CORRELATIONS = {
    ("assists", "points"): (0.129, 0.075, 0.027),
    ("assists", "rebounds"): (0.180, -0.009, -0.007),
    ("assists", "threes"): (0.068, 0.085, 0.013),
    ("points", "rebounds"): (0.260, 0.016, -0.008),
    ("points", "threes"): (0.719, -0.021, 0.008),
    ("rebounds", "threes"): (0.086, 0.005, -0.008),
}
TEAMMATE_RHO, OPPONENT_RHO = CORRELATIONS["points"]
_SEED = 7


@dataclass(frozen=True)
class Leg:
    player: str
    event_id: str
    team: str
    is_over: bool            # over / X+ is True, under is False
    prob: float              # the model's chance this leg hits
    american_odds: float
    label: str = ""
    stat: str = "points"


def joint_probability(legs: list[Leg], teammate_rho: float | None = None,
                      opponent_rho: float | None = None, fast: bool = False) -> float:
    """Chance every leg hits. Passing a correlation overrides the measured
    one for every stat; leaving it out uses the measured value per stat. `fast` trades the
    last few decimals (good to about 1e-5) for speed, for ranking many slips; show people
    the exact one."""
    _validate(legs)
    ordered = sorted(legs, key=lambda leg: leg.event_id)
    joint = 1.0
    for _, group in groupby(ordered, key=lambda leg: leg.event_id):
        joint *= _game_probability(list(group), teammate_rho, opponent_rho, fast)
    return joint


def independent_probability(legs: list[Leg]) -> float:
    """What the chance would be if every leg were independent."""
    return float(np.prod([leg.prob for leg in legs]))


def decimal_odds(legs: list[Leg]) -> float:
    """Standard parlay payout: the product of each leg's decimal odds."""
    return float(np.prod([american_to_decimal(leg.american_odds) for leg in legs]))


def decimal_to_american(decimal: float) -> int:
    if decimal <= 1.0:
        raise ValueError("decimal odds must be above 1")
    return round((decimal - 1.0) * 100.0) if decimal >= 2.0 else round(-100.0 / (decimal - 1.0))


def fair_american(probability: float) -> int:
    p = min(max(probability, 0.001), 0.999)
    return round(-100.0 * p / (1.0 - p)) if p >= 0.5 else round(100.0 * (1.0 - p) / p)


def summarise(legs: list[Leg], teammate_rho: float | None = None,
              opponent_rho: float | None = None, fast: bool = False) -> dict:
    """Everything the builder shows for a slip."""
    joint = joint_probability(legs, teammate_rho, opponent_rho, fast)
    payout = decimal_odds(legs)
    return {
        "legs": len(legs),
        "joint_probability": joint,
        "independent_probability": independent_probability(legs),
        "decimal_odds": payout,
        "payout_per_unit": payout - 1.0,
        "fair_american": fair_american(joint),
        "ev_per_unit": ev_per_unit(joint, payout),
    }


def _validate(legs: list[Leg]) -> None:
    if not legs:
        raise ValueError("a parlay needs at least one leg")
    bets = [(leg.event_id, leg.player, leg.stat) for leg in legs]
    if len(set(bets)) != len(bets):
        raise ValueError("a player can only appear once per stat in a parlay: two bets on the "
                         "same number are not independent")
    if any(not 0.0 < leg.prob < 1.0 for leg in legs):
        raise ValueError("every leg's probability must be strictly between 0 and 1")


def _correlation(a: Leg, b: Leg, teammate_rho: float | None, opponent_rho: float | None) -> float:
    """How two bets in one game move together."""
    if a.stat != b.stat:
        same_player, measured_teammates, measured_opponents = CROSS_CORRELATIONS.get(
            tuple(sorted((a.stat, b.stat))), (0.0, 0.0, 0.0))
        if a.player == b.player:
            return same_player
    else:
        measured_teammates, measured_opponents = CORRELATIONS.get(a.stat, CORRELATIONS["points"])
    if a.team == b.team:
        return measured_teammates if teammate_rho is None else teammate_rho
    return measured_opponents if opponent_rho is None else opponent_rho


FAST_TOLERANCE, EXACT_TOLERANCE = 1e-5, 1e-9


def _game_probability(legs: list[Leg], teammate_rho: float | None,
                      opponent_rho: float | None, fast: bool = False) -> float:
    if len(legs) == 1:
        return legs[0].prob
    signs = np.array([-1.0 if leg.is_over else 1.0 for leg in legs])
    base = np.array([[1.0 if i == j else _correlation(a, b, teammate_rho, opponent_rho)
                      for j, b in enumerate(legs)] for i, a in enumerate(legs)])
    covariance = base * np.outer(signs, signs)
    if np.linalg.eigvalsh(covariance).min() <= 1e-9:
        raise ValueError("these correlations cannot all hold at once for this many legs")
    thresholds = stats.norm.ppf([leg.prob for leg in legs])
    return float(stats.multivariate_normal.cdf(
        thresholds, mean=np.zeros(len(legs)), cov=covariance,
        abseps=FAST_TOLERANCE if fast else EXACT_TOLERANCE,
        releps=FAST_TOLERANCE if fast else EXACT_TOLERANCE, rng=np.random.default_rng(_SEED)))
