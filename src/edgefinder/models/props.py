"""Pitcher strikeout prop model.

Expected strikeouts = recency-weighted K/start over the last
RECENT_STARTS starts, scaled by how strikeout-prone the opposing
lineup is relative to league average.
"""

RECENT_STARTS = 10
RECENCY_DECAY = 0.85  # weight multiplier per start going backwards
MIN_STARTS_REQUIRED = 3
OPPONENT_FACTOR_CAP = (0.85, 1.15)


def weighted_k_per_start(strikeouts_by_start: list[int]) -> float | None:
    """Exponentially weighted average of Ks per start, newest first.

    Returns None when there is not enough history to trust.
    """
    recent = strikeouts_by_start[:RECENT_STARTS]
    if len(recent) < MIN_STARTS_REQUIRED:
        return None
    weight = 1.0
    total_weight = 0.0
    total = 0.0
    for strikeouts in recent:
        total += strikeouts * weight
        total_weight += weight
        weight *= RECENCY_DECAY
    return total / total_weight


def opponent_k_factor(opp_k_per_game: float | None, league_k_per_game: float) -> float:
    """>1 means the opponent strikes out more than league average."""
    if opp_k_per_game is None or league_k_per_game <= 0:
        return 1.0
    factor = opp_k_per_game / league_k_per_game
    low, high = OPPONENT_FACTOR_CAP
    return max(low, min(high, factor))


def expected_strikeouts(
    strikeouts_by_start: list[int],
    opp_k_per_game: float | None,
    league_k_per_game: float,
) -> float | None:
    base = weighted_k_per_start(strikeouts_by_start)
    if base is None:
        return None
    return base * opponent_k_factor(opp_k_per_game, league_k_per_game)
