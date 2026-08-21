import pytest

from edgefinder.betting import poisson


def test_pmf_sums_to_one():
    total = sum(poisson.pmf(k, 8.5) for k in range(80))
    assert total == pytest.approx(1.0, abs=1e-9)


def test_cdf_matches_pmf_sum():
    lam = 6.2
    assert poisson.cdf(5, lam) == pytest.approx(
        sum(poisson.pmf(k, lam) for k in range(6))
    )


def test_half_line_has_no_push():
    probs = poisson.over_under_probs(8.5, 8.5)
    assert probs["push"] == 0.0
    assert probs["over"] + probs["under"] == pytest.approx(1.0)


def test_integer_line_push_probability():
    probs = poisson.over_under_probs(9.0, 8.5)
    assert probs["push"] == pytest.approx(poisson.pmf(9, 8.5))
    assert probs["over"] + probs["under"] + probs["push"] == pytest.approx(1.0)


def test_no_push_probs_normalize():
    probs = poisson.no_push_probs(9.0, 8.5)
    assert probs["over"] + probs["under"] == pytest.approx(1.0)


def test_higher_lambda_raises_over_prob():
    low = poisson.over_under_probs(8.5, 7.0)["over"]
    high = poisson.over_under_probs(8.5, 10.0)["over"]
    assert high > low


def test_invalid_lambda_raises():
    with pytest.raises(ValueError):
        poisson.over_under_probs(8.5, 0.0)
