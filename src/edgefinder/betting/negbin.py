"""Negative-binomial distribution helpers for count stats (points,
rebounds, assists, strikeouts).

Counts like these vary more than a Poisson allows, so a prediction is a
mean plus a dispersion ("size") that controls the extra spread:
variance = mean + mean^2 / dispersion. A huge dispersion collapses back
to Poisson.
"""

import numpy as np
from scipy import stats

MIN_DISPERSION = 0.5
MAX_DISPERSION = 1e6  # effectively Poisson
_MIN_MEAN = 1e-6


def _distribution(mean, dispersion):
    safe_mean = np.maximum(np.asarray(mean, dtype=float), _MIN_MEAN)
    probability = dispersion / (dispersion + safe_mean)
    return stats.nbinom(dispersion, probability)


def estimate_dispersion(means, actuals) -> float:
    """Method-of-moments dispersion from prediction residuals.

    E[(y - mean)^2 - mean] = E[mean^2] / dispersion, so the excess
    variance over Poisson pins the dispersion down. No excess means the
    data is Poisson-like and the dispersion is returned as very large.
    """
    means = np.asarray(means, dtype=float)
    actuals = np.asarray(actuals, dtype=float)
    excess = float(np.mean((actuals - means) ** 2 - means))
    if excess <= 0.0:
        return MAX_DISPERSION
    estimate = float(np.mean(means ** 2)) / excess
    return float(np.clip(estimate, MIN_DISPERSION, MAX_DISPERSION))


def logpmf(count, mean, dispersion):
    return _distribution(mean, dispersion).logpmf(count)


def over_prob(line: float, mean, dispersion):
    """P(count > line). Whole-number lines exclude the push, so a line
    of 20 and a line of 20.5 are the same bet."""
    return _distribution(mean, dispersion).sf(np.floor(line))


def central_interval(mean, dispersion, coverage: float):
    """Lower and upper count bounds of the central `coverage` interval."""
    tail = (1.0 - coverage) / 2.0
    dist = _distribution(mean, dispersion)
    return dist.ppf(tail), dist.ppf(1.0 - tail)
