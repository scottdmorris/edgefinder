import pytest

from edgefinder.models import props


def test_insufficient_history_returns_none():
    assert props.weighted_k_per_start([7, 5]) is None


def test_weighted_average_favors_recent():
    heavy_recent = props.weighted_k_per_start([10, 10, 2, 2, 2])
    heavy_old = props.weighted_k_per_start([2, 2, 2, 10, 10])
    assert heavy_recent > heavy_old


def test_uniform_history_equals_mean():
    assert props.weighted_k_per_start([6, 6, 6, 6]) == pytest.approx(6.0)


def test_opponent_factor_neutral_when_unknown():
    assert props.opponent_k_factor(None, 8.5) == 1.0


def test_opponent_factor_is_capped():
    assert props.opponent_k_factor(20.0, 8.5) == pytest.approx(1.15)
    assert props.opponent_k_factor(1.0, 8.5) == pytest.approx(0.85)


def test_expected_strikeouts_combines_both():
    expected = props.expected_strikeouts([6, 6, 6, 6], 9.35, 8.5)
    assert expected == pytest.approx(6.0 * 1.1)
