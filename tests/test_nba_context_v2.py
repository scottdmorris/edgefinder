import numpy as np
import pandas as pd
import pytest

from edgefinder.betting import negbin
from edgefinder.models import nba_context_points as cp
from edgefinder.models import nba_context_v2 as v2
from edgefinder.models import nba_minutes, nba_shot_features
from edgefinder.tracking import nba_paper
from test_nba_context_points import EVENT, TIP_DATE, ContextEcho, history


def test_the_spread_widens_with_the_projection_and_passes_through_its_measured_points():
    width = v2.MODEL_DISPERSION
    assert callable(width)
    for mean, expected in zip(v2.SPREAD_MEANS, v2.SPREAD_WIDTHS):
        assert width(mean) == pytest.approx(expected)
    assert width(5.0) < width(10.0) < width(15.0) < width(20.0) < width(26.0)
    assert width(1.0) == pytest.approx(v2.SPREAD_WIDTHS[0])      # held flat below the first point


def test_a_low_scorer_is_priced_with_more_spread_than_one_width_for_everyone_would_give():
    # "4+ points" for a 6-point player: P(at least 4) = P(over 3.5)
    fixed = negbin.over_prob(3.5, 6.0, 8.4)
    own = negbin.over_prob(3.5, 6.0, v2.MODEL_DISPERSION)
    assert own < fixed                  # noisier, so a quiet game below 4 is likelier than 8.4 says
    assert 0.0 < own < 1.0


def training(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    columns = set(v2.DIRECT_FEATURES) | set(v2.MINUTES_FEATURES)
    frame = pd.DataFrame({c: np.nan for c in columns}, index=range(n))
    base = rng.uniform(5, 28, n)
    minutes = rng.uniform(15, 36, n)
    frame["min_ewma_mid"] = minutes
    frame["min_ewma_fast"] = minutes
    frame["rate_ewma_05"] = base / 30.0
    frame["rate_ewma_10"] = base / 30.0
    frame["fga_rate_ewma_10"] = base / 60.0
    frame["lost_pts"] = rng.choice([0.0, 12.0, 25.0], n)
    frame["lost_min"] = frame["lost_pts"] * 1.5
    frame["pts"] = rng.poisson(base)
    frame["minutes"] = minutes
    return frame


def test_the_blend_is_exactly_the_average_of_its_two_models():
    model = v2.BlendModel().fit(training())
    test = training(200, seed=1)
    direct = model._direct.predict(test)
    via_minutes = nba_minutes.project_points(test, model._minutes.predict(test))
    assert model.predict(test) == pytest.approx((direct + via_minutes) / 2.0)


def test_blend_predictions_are_never_negative_and_it_remembers_how_much_it_learned_from():
    model = v2.BlendModel().fit(training())
    odd = training(50, seed=2).assign(rate_ewma_05=0.0, rate_ewma_10=0.0)
    assert model.predict(odd).min() > 0.0 and model.n_train > 0


def test_an_untrained_blend_cannot_predict():
    with pytest.raises(RuntimeError):
        v2.BlendModel().predict(training(10))


def test_the_slate_carries_the_shot_inputs_computed_from_earlier_games_only():
    slate = v2.LiveProjector(history(), "2026-27")._build_slate(TIP_DATE)
    assert set(nba_shot_features.SHOT_COLUMNS) <= set(slate.columns)
    cade = slate[slate["player_id"] == 1].iloc[0]
    assert cade["fga_rate_ewma_10"] == pytest.approx(12 / 30)      # 12 shots in 30 minutes, always
    assert cade["fta_rate_ewma_30"] == pytest.approx(4 / 30)
    assert "_upcoming" not in slate.columns


def test_the_live_projector_trains_the_blend_once_and_projects_with_the_shot_slate(monkeypatch):
    trained, seen = [], []

    class Echo(ContextEcho):
        def predict(self, features):
            seen.append(set(features.columns))
            return super().predict(features)

    monkeypatch.setattr(v2, "train", lambda games, season: trained.append(season) or Echo())
    projector = v2.LiveProjector(history(), "2026-27")
    result = projector(EVENT, ["Cade Cunningham", "Joel Embiid"])
    projector({**EVENT, "event_id": "e2"}, ["Cade Cunningham"])
    assert trained == ["2026-27"]
    assert set(result) == {"Cade Cunningham", "Joel Embiid"}
    assert set(nba_shot_features.SHOT_COLUMNS) <= seen[0]


def test_v2_prices_a_line_with_its_own_spread_through_the_real_ledger_builder():
    event = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
             "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
    lines = [{"player": "A", "line": 3.5, "over_odds": -800, "under_odds": 500}]
    rows = nba_paper.build_ledger_rows(
        event, lines, {"A": {"player_id": 1, "mean": 6.0}}, "2026-11-04T17:00:00+00:00",
        "2026-11-04", model_version=v2.MODEL_VERSION, dispersion=v2.MODEL_DISPERSION)
    assert len(rows) == 1 and rows[0]["model_version"] == "context-v2"
    assert rows[0]["model_p_over"] == pytest.approx(negbin.over_prob(3.5, 6.0, v2.MODEL_DISPERSION))
    assert rows[0]["model_p_over"] != pytest.approx(negbin.over_prob(3.5, 6.0, cp.MODEL_DISPERSION))
