import pandas as pd
import pytest

from edgefinder.models import nba_baselines as nb

PRED_COLS = ["pred_season_to_date", "pred_shrunk", "pred_last10", "pred_ewma"]


def make_games(rows):
    """rows: (player_id, season, date, pts, minutes), one row per game."""
    frame = pd.DataFrame(
        rows, columns=["player_id", "season", "game_date", "pts", "minutes"])
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame["game_id"] = [f"g{i:04d}" for i in range(len(frame))]
    return frame


def two_season_player():
    return make_games([
        (1, "2024-25", "2025-01-01", 10, 30.0),
        (1, "2024-25", "2025-01-03", 10, 30.0),
        (1, "2025-26", "2025-10-22", 20, 32.0),
        (1, "2025-26", "2025-10-24", 30, 32.0),
        (1, "2025-26", "2025-10-26", 40, 32.0),
    ])


def predict(frame, **overrides):
    options = {"min_prior_games": 1, **overrides}
    return nb.add_baseline_predictions(frame, "pts", **options)


def current(result):
    return result[result["season"] == "2025-26"].reset_index(drop=True)


def test_shrunk_mean_blends_prior_season_with_games_so_far():
    result = current(predict(two_season_player(), shrink_games=10))
    # prior-season mean is 10; blend = (sum_so_far + 10*10) / (n_so_far + 10)
    assert result["pred_shrunk"].tolist() == pytest.approx(
        [10.0, 120 / 11, 150 / 12])


def test_season_to_date_is_undefined_for_the_first_game():
    result = current(predict(two_season_player()))
    assert pd.isna(result.loc[0, "pred_season_to_date"])
    assert result["pred_season_to_date"].tolist()[1:] == pytest.approx([20.0, 25.0])


def test_n_prior_counts_earlier_games_in_the_same_season():
    result = current(predict(two_season_player()))
    assert result["n_prior"].tolist() == [0, 1, 2]


def test_last_n_mean_uses_only_earlier_games():
    frame = make_games([(1, "2025-26", f"2025-10-{20 + i}", pts, 30.0)
                        for i, pts in enumerate([10, 20, 30, 40])])
    result = predict(frame, recent_window=2, min_recent=1)
    assert pd.isna(result.loc[0, "pred_last10"])
    assert result["pred_last10"].tolist()[1:] == pytest.approx([10.0, 15.0, 25.0])


def test_ewma_weights_recent_games_more():
    frame = make_games([(1, "2025-26", f"2025-10-{20 + i}", pts, 30.0)
                        for i, pts in enumerate([10, 20, 30, 40])])
    result = predict(frame, ewm_alpha=0.5)
    assert result["pred_ewma"].tolist()[1:] == pytest.approx(
        [10.0, 25 / 1.5, 42.5 / 1.75])


def test_a_games_own_result_never_feeds_its_own_prediction():
    base = predict(two_season_player())
    changed_frame = two_season_player()
    changed_frame.loc[3, "pts"] = 999  # middle of the 2025-26 season
    changed = predict(changed_frame)
    # every prediction up to and including that game is untouched...
    pd.testing.assert_frame_equal(
        base.loc[:3, PRED_COLS], changed.loc[:3, PRED_COLS])
    # ...and only later games may react to it
    assert changed.loc[4, "pred_season_to_date"] != base.loc[4, "pred_season_to_date"]


def test_players_are_kept_separate():
    frame = make_games([
        (1, "2025-26", "2025-10-22", 10, 30.0),
        (2, "2025-26", "2025-10-22", 50, 30.0),
        (1, "2025-26", "2025-10-24", 10, 30.0),
        (2, "2025-26", "2025-10-24", 50, 30.0),
    ])
    result = predict(frame).sort_values(["player_id", "game_date"]).reset_index(drop=True)
    assert result.loc[1, "pred_season_to_date"] == 10.0
    assert result.loc[3, "pred_season_to_date"] == 50.0


def test_players_without_enough_prior_games_fall_back_to_league_mean():
    frame = make_games([
        (1, "2024-25", "2025-01-01", 10, 30.0),
        (1, "2024-25", "2025-01-03", 10, 30.0),
        (2, "2024-25", "2025-01-01", 30, 30.0),
        (2, "2024-25", "2025-01-03", 30, 30.0),
        (3, "2025-26", "2025-10-22", 99, 30.0),  # rookie: no prior season
    ])
    result = predict(frame, min_prior_games=5, shrink_games=10)
    rookie = result[result["player_id"] == 3].iloc[0]
    # league mean of 2024-25 is (10+10+30+30)/4 = 20
    assert rookie["pred_shrunk"] == pytest.approx(20.0)


def test_prior_season_minutes_are_attached_for_rotation_filtering():
    result = current(predict(two_season_player()))
    assert result["prior_minutes"].tolist() == pytest.approx([30.0, 30.0, 30.0])
