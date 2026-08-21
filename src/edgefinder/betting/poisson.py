"""Poisson probabilities for totals and strikeout props."""

import math


def pmf(k: int, lam: float) -> float:
    if k < 0:
        return 0.0
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))


def cdf(k: int, lam: float) -> float:
    """P(X <= k)."""
    if k < 0:
        return 0.0
    return sum(pmf(i, lam) for i in range(k + 1))


def over_under_probs(line: float, lam: float) -> dict[str, float]:
    """P(over), P(under), P(push) for a totals-style line.

    Half-point lines cannot push. Integer lines push when the outcome
    lands exactly on the line.
    """
    if lam <= 0:
        raise ValueError("lambda must be positive")
    if line != int(line):
        threshold = math.floor(line)
        over = 1.0 - cdf(threshold, lam)
        return {"over": over, "under": 1.0 - over, "push": 0.0}
    line_int = int(line)
    push = pmf(line_int, lam)
    over = 1.0 - cdf(line_int, lam)
    under = cdf(line_int - 1, lam)
    return {"over": over, "under": under, "push": push}


def no_push_probs(line: float, lam: float) -> dict[str, float]:
    """Over/under probabilities conditional on no push (for EV math,
    since a push refunds the stake)."""
    raw = over_under_probs(line, lam)
    live = raw["over"] + raw["under"]
    return {"over": raw["over"] / live, "under": raw["under"] / live}
