import pytest

from edgefinder.betting import odds_math as om


def test_three_way_sums_to_one():
    fair = om.devig_multiway([0.50, 0.30, 0.28])
    assert sum(fair) == pytest.approx(1.0)


def test_proportions_preserved():
    fair = om.devig_multiway([0.55, 0.55])
    assert fair == pytest.approx([0.5, 0.5])


def test_relative_order_preserved():
    fair = om.devig_multiway([0.48, 0.32, 0.28])
    assert fair[0] > fair[1] > fair[2]


def test_rejects_nonpositive():
    with pytest.raises(ValueError):
        om.devig_multiway([0.5, 0.0, 0.4])
