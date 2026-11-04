import numpy as np
import pandas as pd
import pytest

from edgefinder.models import nba_minutes as nm


def synthetic_features(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    base = rng.uniform(15, 36, n)
    frame = pd.DataFrame({column: np.nan for column in nm.MINUTES_FEATURES}, index=range(n))
    frame["min_ewma_mid"] = base
    frame["min_ewma_fast"] = base + rng.normal(0, 1, n)
    frame["min_ewma_slow"] = base + rng.normal(0, 1, n)
    frame["is_b2b"] = rng.integers(0, 2, n).astype(float)
    frame["is_home"] = rng.integers(0, 2, n).astype(float)
    frame["missed_last10"] = rng.integers(0, 4, n).astype(float)
    # the hidden truth: back-to-backs and recent absences cost minutes
    frame["minutes"] = np.clip(
        base - 4.0 * frame["is_b2b"] - 2.0 * frame["missed_last10"] + rng.normal(0, 1.5, n),
        0, 48)
    return frame


def test_the_model_learns_that_rest_and_absences_change_minutes():
    train, test = synthetic_features(seed=0), synthetic_features(n=800, seed=1)
    model = nm.MinutesModel().fit(train)
    learned = np.abs(model.predict(test) - test["minutes"]).mean()
    naive = np.abs(test["min_ewma_mid"] - test["minutes"]).mean()
    assert learned < 0.6 * naive


def test_predictions_stay_inside_a_real_game():
    train = synthetic_features()
    extreme = synthetic_features(n=50, seed=2).assign(min_ewma_mid=200.0, min_ewma_fast=-50.0)
    predictions = nm.MinutesModel().fit(train).predict(extreme)
    assert predictions.min() >= 0.0
    assert predictions.max() <= nm.MAX_MINUTES


def test_missing_feature_values_are_handled():
    train = synthetic_features()
    row = train.iloc[[0]].copy()
    row[nm.MINUTES_FEATURES] = np.nan
    prediction = nm.MinutesModel().fit(train).predict(row)
    assert np.isfinite(prediction).all()


def test_rows_with_no_minutes_history_are_not_used_for_training():
    train = synthetic_features()
    train.loc[:99, "min_ewma_mid"] = np.nan
    model = nm.MinutesModel().fit(train)
    assert model.n_train == len(train) - 100


def test_a_feature_missing_everywhere_in_training_is_ignored_not_fatal():
    train = synthetic_features().assign(prior_minutes=np.nan)
    model = nm.MinutesModel().fit(train)
    test = synthetic_features(n=100, seed=3)
    with_prior = model.predict(test.assign(prior_minutes=99.0))
    without_prior = model.predict(test.assign(prior_minutes=np.nan))
    assert with_prior.tolist() == without_prior.tolist()


def test_points_are_projected_as_minutes_times_rate():
    features = pd.DataFrame({"rate_ewma_05": [0.5, 0.8]})
    points = nm.project_points(features, np.array([30.0, 20.0]))
    assert points.tolist() == pytest.approx([15.0, 16.0])


def test_predicting_before_fitting_is_an_error():
    with pytest.raises(RuntimeError):
        nm.MinutesModel().predict(synthetic_features(n=5))
