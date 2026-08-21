"""MLB game model: Elo win probability with a starting-pitcher
adjustment, plus a Poisson runs model for totals.

The pitcher adjustment is a deliberate heuristic: one full run of ERA
advantage for your starter shifts the win-probability logit by
PITCHER_LOGIT_PER_ERA. That is roughly consistent with the public
result that upgrading an average starter by 1.00 ERA is worth ~3-4%
win probability. It is capped so a garbage-time spot starter cannot
swing the model absurdly.
"""

import math
from dataclasses import dataclass

PITCHER_LOGIT_PER_ERA = 0.15
MAX_PITCHER_LOGIT_SHIFT = 0.45
LEAGUE_AVG_ERA = 4.10
STARTER_INNINGS_SHARE = 5.5 / 9.0
PITCHER_TOTALS_WEIGHT = 0.5


@dataclass
class TeamRunRates:
    """Season runs scored / allowed per game."""
    scored_per_game: float
    allowed_per_game: float


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def pitcher_adjusted_win_prob(
    elo_home_prob: float,
    home_starter_era: float | None,
    away_starter_era: float | None,
) -> float:
    """Shift the Elo probability for the starting-pitcher matchup.

    Missing ERAs (no probable listed, or a debut) contribute no shift.
    """
    if home_starter_era is None or away_starter_era is None:
        return elo_home_prob
    shift = PITCHER_LOGIT_PER_ERA * (away_starter_era - home_starter_era)
    shift = max(-MAX_PITCHER_LOGIT_SHIFT, min(MAX_PITCHER_LOGIT_SHIFT, shift))
    return _sigmoid(_logit(elo_home_prob) + shift)


def expected_team_runs(
    offense: TeamRunRates,
    defense: TeamRunRates,
    opposing_starter_era: float | None,
) -> float:
    """Expected runs for one team: blend of its offense and the
    opponent's run prevention, nudged by the opposing starter's ERA."""
    base = (offense.scored_per_game + defense.allowed_per_game) / 2.0
    if opposing_starter_era is None:
        return base
    pitcher_delta = (opposing_starter_era - LEAGUE_AVG_ERA) * STARTER_INNINGS_SHARE
    return max(1.5, base + pitcher_delta * PITCHER_TOTALS_WEIGHT)


def expected_game_total(
    home_rates: TeamRunRates,
    away_rates: TeamRunRates,
    home_starter_era: float | None,
    away_starter_era: float | None,
) -> float:
    home_runs = expected_team_runs(home_rates, away_rates, away_starter_era)
    away_runs = expected_team_runs(away_rates, home_rates, home_starter_era)
    return home_runs + away_runs
