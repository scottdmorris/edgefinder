import numpy as np
import pandas as pd
import pytest

from edgefinder.models import nba_shot_features as shots


def games(rows):
    return pd.DataFrame(rows).assign(game_date=lambda d: pd.to_datetime(d["game_date"]))


def log(day, minutes, pts, fga, fta, season="2026-27", player_id=1):
    return {"player_id": player_id, "game_date": day, "season": season, "minutes": minutes,
            "pts": pts, "fga": fga, "fta": fta}


def test_the_first_game_has_no_history_so_every_shot_feature_is_empty():
    out = shots.add_shot_features(games([log("2026-11-01", 30, 20, 15, 5)]))
    assert out[shots.SHOT_COLUMNS].isna().all().all()


def test_a_game_never_sees_its_own_shots():
    # game 2 may only know game 1: 15 shots in 30 min = 0.5 per minute, 6 free throws = 0.2
    out = shots.add_shot_features(games([log("2026-11-01", 30, 20, 15, 6),
                                         log("2026-11-03", 30, 99, 99, 99)]))
    second = out.iloc[1]
    assert second["fga_rate_ewma_10"] == pytest.approx(0.5)
    assert second["fta_rate_ewma_30"] == pytest.approx(0.2)
    assert second["pts_season_rate"] == pytest.approx(20 / 30)


def test_the_smoothed_rate_leans_towards_the_most_recent_game():
    # rates 0.5 then 1.0; ewma(alpha 0.3, adjust) after both = (1.0*0.7 + 0.5... computed by hand:
    # weights 0.7 (older) and 1 (newer): (0.5*0.7 + 1.0*1) / 1.7 = 0.79411...
    out = shots.add_shot_features(games([log("2026-11-01", 30, 20, 15, 5),
                                         log("2026-11-03", 30, 30, 30, 5),
                                         log("2026-11-05", 30, 25, 10, 5)]))
    assert out.iloc[2]["fga_rate_ewma_30"] == pytest.approx((0.5 * 0.7 + 1.0) / 1.7)


def test_steadiness_needs_three_games_and_is_the_standard_deviation_of_earlier_scores():
    rows = [log(f"2026-11-0{d}", 30, p, 10, 4) for d, p in enumerate([10, 20, 30, 99], start=1)]
    out = shots.add_shot_features(games(rows))
    assert np.isnan(out.iloc[2]["pts_std10"])                  # only two earlier games
    assert out.iloc[3]["pts_std10"] == pytest.approx(10.0)     # std of 10, 20, 30 (n-1) is 10


def test_a_new_season_restarts_the_season_rate_but_keeps_the_shot_habit():
    out = shots.add_shot_features(games([log("2026-04-01", 30, 24, 20, 4, season="2025-26"),
                                         log("2026-11-01", 30, 10, 5, 2, season="2026-27")]))
    new = out.iloc[1]
    assert np.isnan(new["pts_season_rate"])                    # no games yet this season
    assert new["fga_rate_ewma_10"] == pytest.approx(20 / 30)   # last season's habit carries over


def test_players_never_mix_and_zero_minute_games_do_not_divide_by_zero():
    out = shots.add_shot_features(games([
        log("2026-11-01", 0, 0, 0, 0, player_id=1), log("2026-11-03", 30, 10, 6, 2, player_id=1),
        log("2026-11-01", 20, 8, 4, 0, player_id=2), log("2026-11-03", 20, 8, 4, 0, player_id=2)]))
    one = out[out["player_id"] == 1].iloc[1]
    assert np.isnan(one["fga_rate_ewma_10"])      # his only earlier game had no minutes: no rate
    assert np.isnan(one["pts_season_rate"])       # and no minutes to divide points by
    two = out[out["player_id"] == 2].iloc[1]
    assert two["fga_rate_ewma_10"] == pytest.approx(4 / 20)
