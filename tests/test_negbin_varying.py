import numpy as np
import pytest

from edgefinder.betting import negbin


def test_a_constant_function_gives_exactly_the_same_probabilities_as_the_number():
    flat = negbin.varying([5.0, 25.0], [8.0, 8.0])
    for mean in (3.0, 12.5, 30.0):
        assert negbin.over_prob(14.5, mean, flat) == pytest.approx(negbin.over_prob(14.5, mean, 8.0))
        assert negbin.logpmf(10, mean, flat) == pytest.approx(negbin.logpmf(10, mean, 8.0))


def test_it_runs_straight_lines_between_the_points_and_holds_flat_beyond_them():
    f = negbin.varying([8.0, 12.0, 22.0], [2.0, 4.0, 14.0])
    assert f(8.0) == pytest.approx(2.0) and f(12.0) == pytest.approx(4.0)
    assert f(10.0) == pytest.approx(3.0)             # halfway between 2 and 4
    assert f(17.0) == pytest.approx(9.0)             # halfway between 4 and 14
    assert f(1.0) == pytest.approx(2.0) and f(40.0) == pytest.approx(14.0)


def test_each_player_in_one_call_gets_the_width_for_his_own_projection():
    f = negbin.varying([5.0, 25.0], [2.0, 14.0])
    means = np.array([5.0, 25.0])
    together = negbin.over_prob(9.5, means, f)
    assert together[0] == pytest.approx(negbin.over_prob(9.5, 5.0, 2.0))
    assert together[1] == pytest.approx(negbin.over_prob(9.5, 25.0, 14.0))


def test_a_noisier_low_scorer_has_a_fatter_tail_than_one_fixed_width_gives():
    # a 6-point projection: width 2.3 puts more chance on a 15+ game than a width of 8.4
    narrow_world = negbin.over_prob(14.5, 6.0, 8.4)
    realistic = negbin.over_prob(14.5, 6.0, negbin.varying([6.0, 25.0], [2.3, 14.0]))
    assert realistic > narrow_world


@pytest.mark.parametrize("means, widths", [
    ([5.0], [2.0]),                 # needs two points
    ([5.0, 5.0], [2.0, 3.0]),       # not increasing
    ([9.0, 5.0], [2.0, 3.0]),       # decreasing
    ([5.0, 9.0], [2.0]),            # mismatched
    ([5.0, 9.0], [2.0, 0.0]),       # non-positive width
])
def test_bad_points_are_refused(means, widths):
    with pytest.raises(ValueError):
        negbin.varying(means, widths)
