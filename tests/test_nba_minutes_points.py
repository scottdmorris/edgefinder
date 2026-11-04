import datetime as dt

import pandas as pd
import pytest

from edgefinder.models import nba_features, nba_minutes, nba_minutes_points as mp

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
TIP_DATE = "2026-11-04"


def history():
    """Three current-season players, one player who only has last season's
    games, 25 games last season (so priors exist) and 8 this season."""
    rows = []
    people = [(1, "Cade Cunningham", "DET"), (2, "Joel Embiid", "PHI"),
              (3, "Somebody Else", "BOS"), (4, "Left The League", "DET")]
    for player_id, name, team in people:
        for i in range(25):
            date = pd.Timestamp("2025-12-01") + pd.Timedelta(days=i)
            rows.append((player_id, name, team, f"{team}-old-{i}", date, "2025-26",
                         30.0, 15.0, i % 2 == 0))
        if player_id == 4:
            continue
        for i in range(8):
            date = pd.Timestamp("2026-10-19") + pd.Timedelta(days=2 * i)   # last game: Nov 2
            minutes = 31.0 if (player_id == 1 and i == 7) else 30.0
            rows.append((player_id, name, team, f"{team}-new-{i}", date, "2026-27",
                         minutes, 15.0, i % 2 == 0))
    return pd.DataFrame(rows, columns=[
        "player_id", "player_name", "team", "game_id", "game_date", "season",
        "minutes", "pts", "is_home"])


def slate():
    return mp.build_slate_features(history(), season="2026-27", game_date=TIP_DATE)


def test_the_slate_has_one_row_per_player_who_has_played_this_season():
    frame = slate()
    assert sorted(frame["player_id"]) == [1, 2, 3]
    assert frame.loc[frame["player_id"] == 4].empty


def test_slate_rows_carry_the_latest_team_and_name():
    row = slate().set_index("player_id").loc[1]
    assert row["team"] == "DET"
    assert row["player_name"] == "Cade Cunningham"


def test_slate_features_reflect_games_played_so_far():
    row = slate().set_index("player_id").loc[1]
    assert row["min_last1"] == 31.0              # his most recent game
    assert row["n_prior_season"] == 8            # games already played this season
    last_game = pd.Timestamp("2026-11-02")
    assert row["rest_days"] == (pd.Timestamp(TIP_DATE) - last_game).days == 2
    assert row["rest_days"] <= nba_features.MAX_REST_DAYS


def test_building_the_slate_does_not_modify_the_history():
    frame = history()
    before = frame.copy()
    mp.build_slate_features(frame, season="2026-27", game_date=TIP_DATE)
    pd.testing.assert_frame_equal(frame, before)


class HomeBonusModel:
    """Stands in for the trained model: 30 minutes, plus 5 at home."""

    def predict(self, features):
        return 30.0 + 5.0 * features["is_home"].to_numpy()


def test_projection_is_minutes_times_rate_with_the_home_flag_set_per_game():
    frame = slate()
    projections = mp.project_event(
        EVENT, ["Cade Cunningham", "Joel Embiid"], frame, HomeBonusModel())
    rates = frame.set_index("player_id")["rate_ewma_05"]
    assert projections["Cade Cunningham"]["mean"] == pytest.approx(35.0 * rates[1])   # at home
    assert projections["Joel Embiid"]["mean"] == pytest.approx(30.0 * rates[2])       # away
    assert projections["Cade Cunningham"]["player_id"] == 1


def test_only_players_in_the_game_are_projected():
    projections = mp.project_event(
        EVENT, ["Cade Cunningham", "Somebody Else", "Nobody Real"], slate(), HomeBonusModel())
    assert set(projections) == {"Cade Cunningham"}


def test_players_with_no_scoring_history_are_left_out():
    frame = slate()
    frame.loc[frame["player_id"] == 2, "rate_ewma_05"] = float("nan")
    projections = mp.project_event(
        EVENT, ["Cade Cunningham", "Joel Embiid"], frame, HomeBonusModel())
    assert set(projections) == {"Cade Cunningham"}


def test_the_live_projector_trains_once_and_reuses_the_model(monkeypatch):
    trained = []
    real_train = mp.train

    def counting_train(games, season):
        trained.append(season)
        return real_train(games, season)

    monkeypatch.setattr(mp, "train", counting_train)
    projector = mp.LiveProjector(history(), "2026-27")
    first = projector(EVENT, ["Cade Cunningham", "Joel Embiid"])
    second = projector(EVENT, ["Cade Cunningham"])
    assert trained == ["2026-27"]
    assert set(first) == {"Cade Cunningham", "Joel Embiid"}
    assert second["Cade Cunningham"]["mean"] == pytest.approx(first["Cade Cunningham"]["mean"])


def test_the_live_projector_remembers_a_training_failure(monkeypatch):
    attempts = []

    def failing_train(games, season):
        attempts.append(1)
        raise RuntimeError("not enough data")

    monkeypatch.setattr(mp, "train", failing_train)
    projector = mp.LiveProjector(history(), "2026-27")
    for _ in range(3):
        with pytest.raises(RuntimeError, match="not enough data"):
            projector(EVENT, ["Cade Cunningham"])
    assert len(attempts) == 1   # no retraining attempt on every game


def test_the_live_projector_builds_one_slate_per_game_date(monkeypatch):
    built = []
    real_slate = mp.build_slate_features

    def counting_slate(games, season, game_date):
        built.append(game_date)
        return real_slate(games, season, game_date)

    monkeypatch.setattr(mp, "build_slate_features", counting_slate)
    projector = mp.LiveProjector(history(), "2026-27")
    projector(EVENT, ["Cade Cunningham"])
    projector({**EVENT, "event_id": "e2"}, ["Joel Embiid"])
    assert built == ["2026-11-04"]


def test_training_returns_a_fitted_model():
    model = mp.train(history(), season="2026-27")
    assert isinstance(model, nba_minutes.MinutesModel)
    assert model.n_train > 0
    predictions = model.predict(slate())
    assert len(predictions) == 3
