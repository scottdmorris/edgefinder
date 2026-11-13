"""Odds conversions and vig removal.

All probabilities are expressed in [0, 1]. American odds are ints like
-150 or +130. Decimal odds include the stake (e.g. -150 -> 1.667).
"""


def american_to_decimal(american: float) -> float:
    if american == 0:
        raise ValueError("American odds cannot be 0")
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def decimal_to_american(decimal: float) -> float:
    if decimal <= 1.0:
        raise ValueError("Decimal odds must be > 1.0")
    if decimal >= 2.0:
        return (decimal - 1.0) * 100.0
    return -100.0 / (decimal - 1.0)


def implied_prob(american: float) -> float:
    """Probability implied by the quoted price, vig included."""
    return 1.0 / american_to_decimal(american)


def prob_to_decimal(prob: float) -> float:
    if not 0.0 < prob < 1.0:
        raise ValueError("Probability must be in (0, 1)")
    return 1.0 / prob


def prob_to_american(prob: float) -> float:
    """Fair American odds for a given true probability."""
    return decimal_to_american(prob_to_decimal(prob))


def devig_two_way(prob_a: float, prob_b: float) -> tuple[float, float]:
    """Remove vig from a two-way market by proportional normalization.

    Inputs are the vig-included implied probabilities of each side
    (they will sum to > 1). Returns fair probabilities summing to 1.
    """
    total = prob_a + prob_b
    if total <= 0 or prob_a < 0 or prob_b < 0:
        raise ValueError("Implied probabilities must be positive")
    return prob_a / total, prob_b / total


def devig_multiway(implied_probs: list[float]) -> list[float]:
    """Remove vig from an n-way market (e.g. soccer's win/draw/win) by
    proportional normalization."""
    total = sum(implied_probs)
    if total <= 0 or any(p <= 0 for p in implied_probs):
        raise ValueError("Implied probabilities must be positive")
    return [p / total for p in implied_probs]


def market_hold(prob_a: float, prob_b: float) -> float:
    """The bookmaker's hold (overround) on a two-way market."""
    return prob_a + prob_b - 1.0
