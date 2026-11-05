import numpy as np
import pandas as pd
import pytest

from edgefinder.data import nba_injuries
from edgefinder.models import nba_context, nba_context_points as cp

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
TIP_DATE = "2026-11-04"


def history():
    """DET and PHI, a prior season and 8 games this season. Player 5 (a DET
    rotation player) shows up on the recent roster so he can be ruled out."""
    rows = []
    people = [(1, "Cade Cunningham", "DET", "PHI"), (2, "Joel Embiid", "PHI", "DET"),
              (5, "Out Tonight", "DET", "PHI")]
    for player_id, name, team, opponent in people:
        for i in range(25):
            rows.append((player_id, name, team, opponent, f"{team}-old-{i}",
                         pd.Timestamp("2025-12-01") + pd.Timedelta(days=i), "2025-26", 30.0, 15.0))
        for i in range(8):
            rows.append((player_id, name, team, opponent, f"{team}-new-{i}",
                         pd.Timestamp("2026-10-19") + pd.Timedelta(days=2 * i), "2026-27",
                         30.0, 15.0))
    frame = pd.DataFrame(rows, columns=[
        "player_id", "player_name", "team", "opponent", "game_id", "game_date", "season",
        "minutes", "pts"])
    # every player on a team shares a game id per date, as in a real box score
    frame["game_id"] = frame["team"] + frame["game_date"].dt.strftime("%Y%m%d")
    frame["game_id"] = frame["game_id"].str.replace(r"^(DET|PHI)", "", regex=True)
    frame["is_home"] = frame["team"] == "DET"
    return frame.assign(fga=12, fta=4, tov=2)


def slate():
    from edgefinder.models import nba_minutes_points
    return nba_minutes_points.build_slate_features(history(), "2026-27", TIP_DATE)


class ContextEcho:
    """Stands in for the model: 10 points, plus a tenth of the minutes lost."""

    def predict(self, features):
        return 10.0 + 0.1 * features["lost_min"].fillna(0.0).to_numpy()


def test_the_projection_uses_the_context_for_the_players_own_team():
    context = {"DET": {"lost_min": 40.0, "lost_pts": 20.0, "lost_starters": 1.0, "n_absent": 1.0,
                       "opp_def_rel": 1.0, "pace_rel": 1.0},
               "PHI": {"lost_min": 0.0, "lost_pts": 0.0, "lost_starters": 0.0, "n_absent": 0.0,
                       "opp_def_rel": 1.0, "pace_rel": 1.0}}
    result = cp.project_event(EVENT, ["Cade Cunningham", "Joel Embiid"], slate(), ContextEcho(),
                              context)
    assert result["Cade Cunningham"]["mean"] == pytest.approx(14.0)     # DET lost 40 minutes
    assert result["Joel Embiid"]["mean"] == pytest.approx(10.0)         # PHI lost none


def test_a_team_with_no_context_is_projected_as_if_nothing_is_missing():
    result = cp.project_event(EVENT, ["Cade Cunningham"], slate(), ContextEcho(), {})
    assert result["Cade Cunningham"]["mean"] == pytest.approx(10.0)


def test_only_players_in_the_game_with_scoring_history_are_projected():
    frame = slate()
    frame.loc[frame["player_id"] == 2, "rate_ewma_05"] = float("nan")
    result = cp.project_event(EVENT, ["Cade Cunningham", "Joel Embiid", "Nobody Real"], frame,
                              ContextEcho(), {})
    assert set(result) == {"Cade Cunningham"}


def test_a_model_that_has_not_been_trained_cannot_predict():
    with pytest.raises(RuntimeError):
        cp.PointsModel().predict(slate())


def synthetic_training(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({c: np.nan for c in cp.FEATURES}, index=range(n))
    base = rng.uniform(5, 28, n)
    frame["min_ewma_mid"] = rng.uniform(15, 36, n)
    frame["rate_ewma_05"] = base / 30.0
    frame["rate_ewma_10"] = base / 30.0
    frame["lost_pts"] = rng.choice([0.0, 0.0, 12.0, 20.0, 30.0], n)
    frame["lost_min"] = frame["lost_pts"] * 1.5
    frame["pts"] = rng.poisson(base + 0.25 * frame["lost_pts"])
    return frame


def test_the_model_learns_that_missing_teammates_mean_more_points():
    train, test = synthetic_training(seed=0), synthetic_training(1000, seed=1)
    model = cp.PointsModel().fit(train)
    quiet = test.assign(lost_pts=0.0, lost_min=0.0)
    busy = test.assign(lost_pts=30.0, lost_min=45.0)
    assert (model.predict(busy) - model.predict(quiet)).mean() > 3.0     # truth: +7.5


def test_predictions_are_never_negative():
    model = cp.PointsModel().fit(synthetic_training())
    odd = synthetic_training(100, seed=2).assign(rate_ewma_05=0.0, rate_ewma_10=0.0)
    assert model.predict(odd).min() > 0.0


def test_an_input_missing_from_every_training_row_is_ignored_not_fatal():
    train = synthetic_training().assign(opp_def_rel=np.nan, pace_rel=np.nan)
    model = cp.PointsModel().fit(train)
    assert "opp_def_rel" not in model._columns and model.n_train > 0


def test_the_live_projector_trains_once_and_reads_the_injury_report_once(monkeypatch):
    trained, reports = [], []

    def fake_train(games, season):
        trained.append(season)
        return ContextEcho()

    def report():
        reports.append(1)
        return [nba_injuries.Injury("Out Tonight", "DET", "Out", "")]

    monkeypatch.setattr(cp, "train", fake_train)
    projector = cp.LiveProjector(history(), "2026-27", injuries=report)
    first = projector(EVENT, ["Cade Cunningham", "Joel Embiid"])
    projector({**EVENT, "event_id": "e2"}, ["Cade Cunningham"])
    assert trained == ["2026-27"] and len(reports) == 1
    # the injury report removed minutes from DET (player 5 plays 30 a night), not from PHI
    assert first["Cade Cunningham"]["mean"] > first["Joel Embiid"]["mean"]


def test_a_missing_injury_report_does_not_stop_the_projection(monkeypatch):
    monkeypatch.setattr(cp, "train", lambda games, season: ContextEcho())

    def broken():
        raise nba_injuries.InjuryDataError("down")

    projector = cp.LiveProjector(history(), "2026-27", injuries=broken)
    result = projector(EVENT, ["Cade Cunningham"])
    assert result["Cade Cunningham"]["mean"] == pytest.approx(10.0)    # nobody known to be out


def test_without_an_injury_source_nobody_is_out(monkeypatch):
    monkeypatch.setattr(cp, "train", lambda games, season: ContextEcho())
    result = cp.LiveProjector(history(), "2026-27")(EVENT, ["Cade Cunningham"])
    assert result["Cade Cunningham"]["mean"] == pytest.approx(10.0)


def test_the_live_projector_remembers_a_training_failure(monkeypatch):
    attempts = []

    def failing(games, season):
        attempts.append(1)
        raise RuntimeError("not enough data")

    monkeypatch.setattr(cp, "train", failing)
    projector = cp.LiveProjector(history(), "2026-27")
    for _ in range(3):
        with pytest.raises(RuntimeError, match="not enough data"):
            projector(EVENT, ["Cade Cunningham"])
    assert len(attempts) == 1


def test_training_on_real_shaped_history_returns_a_fitted_model():
    model = cp.train(history(), season="2026-27")
    assert isinstance(model, cp.PointsModel) and model.n_train > 0
    assert (model.predict(nba_context.add_context(slate(), history()).assign(is_home=1.0)) > 0).all()
