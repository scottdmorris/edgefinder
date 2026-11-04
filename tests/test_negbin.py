import numpy as np
import pytest

from edgefinder.betting import negbin


def test_over_prob_decreases_as_line_rises():
    probs = [negbin.over_prob(line, 20.0, 8.0) for line in (14.5, 19.5, 24.5, 29.5)]
    assert probs == sorted(probs, reverse=True)


def test_over_prob_is_balanced_when_line_equals_mean():
    assert 0.4 < negbin.over_prob(20.0, 20.0, 8.0) < 0.6


def test_over_prob_excludes_pushes_on_whole_number_lines():
    # P(X > 20) must equal P(X >= 21), and a .5 line just below gives the same
    assert negbin.over_prob(20.0, 20.0, 8.0) == pytest.approx(
        negbin.over_prob(20.5, 20.0, 8.0))


def test_logpmf_sums_to_one():
    total = sum(np.exp(negbin.logpmf(k, 12.0, 5.0)) for k in range(0, 300))
    assert total == pytest.approx(1.0, abs=1e-6)


def test_estimate_dispersion_recovers_known_value():
    rng = np.random.default_rng(0)
    mean, size = 20.0, 5.0
    draws = rng.negative_binomial(size, size / (size + mean), size=50_000)
    estimated = negbin.estimate_dispersion(np.full(draws.shape, mean), draws)
    assert estimated == pytest.approx(size, rel=0.15)


def test_estimate_dispersion_for_poisson_like_data_is_large():
    rng = np.random.default_rng(1)
    draws = rng.poisson(10.0, size=50_000)
    assert negbin.estimate_dispersion(np.full(draws.shape, 10.0), draws) > 200


def test_central_interval_brackets_the_mean():
    low, high = negbin.central_interval(20.0, 8.0, 0.8)
    assert low < 20.0 < high


def test_zero_mean_does_not_blow_up():
    assert np.isfinite(negbin.logpmf(0, 0.0, 5.0))
