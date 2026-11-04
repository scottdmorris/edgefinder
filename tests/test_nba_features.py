import numpy as np
import pandas as pd
import pytest

from edgefinder.models import nba_features as nf


def games(rows):
    """rows: (player_id, team, game_id, 'YYYY-MM-DD', season, minutes, pts, is_home)"""
    frame = pd.DataFrame(rows, columns=[
        "player_id", "team", "game_id", "game_date", "season", "minutes", "pts", "is_home"])
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    return frame


def single_player(minutes, points=None, start="2025-10-20", gap_days=2, team="AAA"):
    points = points or [m / 2 for m in minutes]
    rows = []
    for i, (m, p) in enumerate(zip(minutes, points)):
        date = (pd.Timestamp(start) + pd.Timedelta(days=gap_days * i)).strftime("%Y-%m-%d")
        rows.append((1, team, f"g{i:03d}", date, "2025-26", float(m), float(p), i % 2 == 0))
    return games(rows)


def build(frame):
    return nf.build_features(frame).reset_index(drop=True)


def test_minute_averages_use_only_earlier_games():
    features = build(single_player([30, 20, 40, 10]))
    assert pd.isna(features.loc[0, "min_last1"])
    assert features["min_last1"].tolist()[1:] == [30.0, 20.0, 40.0]
    assert features["min_last3"].tolist()[1:] == pytest.approx([30.0, 25.0, 30.0])


def test_exponential_minute_averages_match_pandas():
    minutes = [30, 20, 40, 10, 35]
    features = build(single_player(minutes))
    expected = pd.Series(minutes).shift(1).ewm(alpha=0.3, adjust=True, ignore_na=False).mean()
    assert features["min_ewma_mid"].tolist()[1:] == pytest.approx(expected.tolist()[1:])


def test_a_games_own_result_never_feeds_its_own_features():
    base = build(single_player([30, 20, 40, 10, 35, 25]))
    altered_frame = single_player([30, 20, 40, 10, 35, 25])
    altered_frame.loc[3, ["minutes", "pts"]] = [48.0, 99.0]
    altered = build(altered_frame)
    feature_columns = [c for c in nf.FEATURE_COLUMNS if c in base.columns]
    pd.testing.assert_frame_equal(base.loc[:3, feature_columns], altered.loc[:3, feature_columns])
    assert altered.loc[4, "min_last1"] != base.loc[4, "min_last1"]


def test_rest_days_and_back_to_back_flag():
    frame = games([
        (1, "AAA", "g1", "2025-10-20", "2025-26", 30.0, 15.0, True),
        (1, "AAA", "g2", "2025-10-21", "2025-26", 30.0, 15.0, False),
        (1, "AAA", "g3", "2025-10-24", "2025-26", 30.0, 15.0, True),
    ])
    features = build(frame)
    assert pd.isna(features.loc[0, "rest_days"])
    assert features["rest_days"].tolist()[1:] == [1.0, 3.0]
    assert features["is_b2b"].tolist()[1:] == [1.0, 0.0]


def test_rest_days_are_capped_so_offseason_gaps_do_not_dominate():
    frame = games([
        (1, "AAA", "g1", "2025-04-10", "2024-25", 30.0, 15.0, True),
        (1, "AAA", "g2", "2025-10-22", "2025-26", 30.0, 15.0, True),
    ])
    assert build(frame).loc[1, "rest_days"] == nf.MAX_REST_DAYS


def test_games_in_the_last_week_counts_only_earlier_games_inside_seven_days():
    frame = games([
        (1, "AAA", f"g{i}", d, "2025-26", 30.0, 15.0, True)
        for i, d in enumerate(["2025-10-20", "2025-10-22", "2025-10-24", "2025-10-30"])
    ])
    features = build(frame)
    # Oct 30 looks back to Oct 23: only the Oct 24 game is inside the week
    assert features["games_last_7d"].tolist() == [0.0, 1.0, 2.0, 1.0]


def test_prior_season_minutes_come_from_last_season_only():
    rows = [(1, "AAA", f"a{i}", f"2024-12-{i + 1:02d}", "2024-25", 20.0, 10.0, True)
            for i in range(25)]
    rows += [(1, "AAA", "b0", "2025-11-01", "2025-26", 30.0, 15.0, True)]
    features = build(games(rows))
    assert features.loc[25, "prior_minutes"] == pytest.approx(20.0)
    assert pd.isna(features.loc[0, "prior_minutes"])


def team_season(player_games_idx, n_team_games=12, team="AAA"):
    """One player's games within a team's schedule of n_team_games, plus a
    teammate (id 2) who plays every game so the schedule is complete."""
    rows = []
    for i in range(n_team_games):
        date = (pd.Timestamp("2025-10-20") + pd.Timedelta(days=2 * i)).strftime("%Y-%m-%d")
        rows.append((2, team, f"g{i:03d}", date, "2025-26", 30.0, 15.0, True))
        if i in player_games_idx:
            rows.append((1, team, f"g{i:03d}", date, "2025-26", 30.0, 15.0, True))
    return games(rows)


def missed_for(frame, player_id=1):
    features = build(frame)
    return features[features["player_id"] == player_id].reset_index(drop=True)["missed_last10"]


def test_missed_games_count_recent_team_games_the_player_sat_out():
    played = {0, 1, 2, 3, 4, 5, 9, 10, 11}
    missed = missed_for(team_season(played))
    # appearances at team indexes 0-5, 9, 10, 11; look at the 9th appearance (idx 11)
    # window = team games idx 1..10: played 1-5 and 9, 10 = 7 of 10 -> missed 3
    assert missed.tolist()[-1] == 3
    # idx 9: window idx 0..8, played 0-5 = 6 of 9 -> missed 3
    assert missed.tolist()[6] == 3


def test_a_player_who_never_misses_has_zero_missed_games():
    missed = missed_for(team_season(set(range(12))))
    assert pd.isna(missed.iloc[0])           # no history with the team yet
    assert missed.iloc[1:].eq(0).all()


def test_a_traded_player_is_not_penalised_for_games_before_the_trade():
    old_team = [(1, "OLD", f"o{i}", f"2025-10-{20 + 2 * i}", "2025-26", 30.0, 15.0, True)
                for i in range(5)]
    old_schedule = [(2, "OLD", f"o{i}", f"2025-10-{20 + 2 * i}", "2025-26", 30.0, 15.0, True)
                    for i in range(5)]
    new_schedule = [(3, "NEW", f"n{i}", f"2025-11-{1 + 2 * i:02d}", "2025-26", 30.0, 15.0, True)
                    for i in range(12)]
    new_team = [(1, "NEW", f"n{i}", f"2025-11-{1 + 2 * i:02d}", "2025-26", 30.0, 15.0, True)
                for i in range(8, 12)]
    features = build(games(old_team + old_schedule + new_schedule + new_team))
    mine = features[features["player_id"] == 1].reset_index(drop=True)
    assert pd.isna(mine.loc[5, "missed_last10"])    # first game for the new team
    assert mine.loc[6:, "missed_last10"].eq(0).all()


def test_minutes_weighted_scoring_rate_tracks_points_per_minute():
    features = build(single_player([20, 20, 20], points=[10, 10, 10]))
    assert features["rate_ewma_10"].tolist()[1:] == pytest.approx([0.5, 0.5])


def test_home_flag_is_passed_through_as_a_number():
    features = build(single_player([30, 30, 30]))
    assert features["is_home"].tolist() == [1.0, 0.0, 1.0]


def test_the_input_frame_is_not_modified():
    frame = single_player([30, 20, 40])
    before = frame.copy()
    build(frame)
    pd.testing.assert_frame_equal(frame, before)
