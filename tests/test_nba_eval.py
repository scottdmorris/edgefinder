import pandas as pd
import pytest

from edgefinder.eval import nba_eval


def frame(actual, predicted, n_prior=None, prior_minutes=None):
    data = {"pts": actual, "pred_a": predicted}
    if n_prior is not None:
        data["n_prior"] = n_prior
    if prior_minutes is not None:
        data["prior_minutes"] = prior_minutes
    return pd.DataFrame(data)


def test_perfect_predictions_have_zero_error():
    scores = nba_eval.score_predictions(frame([10, 20, 30], [10, 20, 30]), "pred_a", "pts")
    assert scores["mae"] == 0.0
    assert scores["rmse"] == 0.0
    assert scores["bias"] == 0.0
    assert scores["n"] == 3


def test_bias_is_positive_when_over_predicting():
    scores = nba_eval.score_predictions(frame([10, 10], [14, 16]), "pred_a", "pts")
    assert scores["bias"] == pytest.approx(5.0)
    assert scores["mae"] == pytest.approx(5.0)


def test_rows_without_a_prediction_are_ignored():
    scores = nba_eval.score_predictions(
        frame([10, 20, 30], [float("nan"), 20, 30]), "pred_a", "pts")
    assert scores["n"] == 2
    assert scores["mae"] == 0.0


def test_sharper_correct_predictions_score_a_better_log_score():
    actual = [10, 20, 30, 20, 10, 30]
    good = nba_eval.score_predictions(frame(actual, actual), "pred_a", "pts")
    bad = nba_eval.score_predictions(
        frame(actual, [20, 20, 20, 20, 20, 20]), "pred_a", "pts")
    assert good["log_score"] > bad["log_score"]


def test_interval_coverages_are_proportions():
    actual = [8, 12, 15, 9, 11, 14, 10, 13]
    scores = nba_eval.score_predictions(frame(actual, [11] * 8), "pred_a", "pts")
    assert 0.0 <= scores["cov50"] <= scores["cov80"] <= 1.0


def test_mae_is_split_by_games_played_bucket():
    data = frame(
        actual=[10, 10, 10, 10],
        predicted=[12, 14, 11, 10],
        n_prior=[0, 3, 10, 30],
    )
    table = nba_eval.score_by_games_played(
        data, ["pred_a"], "pts", edges=(0, 5, 20, 10_000))
    assert table["pred_a"].tolist() == pytest.approx([3.0, 1.0, 0.0])
    assert list(table.index) == ["0-4 games", "5-19 games", "20+ games"]


def test_rotation_filter_uses_prior_season_minutes_only():
    data = frame([10, 10, 10], [10, 10, 10], prior_minutes=[35.0, 12.0, float("nan")])
    kept = nba_eval.rotation_players(data, min_prior_minutes=20.0)
    assert kept["prior_minutes"].tolist() == [35.0]
