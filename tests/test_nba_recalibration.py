import json

import pandas as pd
import pytest

from edgefinder.models import nba_recalibration as rc
from edgefinder.tracking import nba_alt, nba_paper, nba_parlay

CURVES = {"ewma-v1": {"bench": {"x": [0.0, 0.5, 0.8, 1.0], "y": [0.0, 0.45, 0.70, 0.90]}}}


@pytest.mark.parametrize("minutes, role", [
    (5, "bench"), (17.9, "bench"), (18, "rotation"), (27.9, "rotation"), (28, "starter"),
    (44, "starter"), (None, None), (float("nan"), None), ("x", None)])
def test_a_players_role_comes_from_his_recent_minutes(minutes, role):
    assert rc.role_for(minutes) == role


def test_a_chance_is_bent_along_the_curve_for_that_model_and_role():
    # 0.8 on the bench curve becomes 0.70; 0.65 is halfway between 0.5 and 0.8 -> 0.575
    assert rc.calibrate("ewma-v1", 0.8, 12, CURVES) == pytest.approx(0.70)
    assert rc.calibrate("ewma-v1", 0.65, 12, CURVES) == pytest.approx(0.575)


def test_no_curve_for_the_model_role_or_minutes_leaves_the_chance_alone():
    assert rc.calibrate("ewma-v1", 0.8, 30, CURVES) == 0.8          # no starter curve here
    assert rc.calibrate("minutes-v1", 0.8, 12, CURVES) == 0.8       # no curve for this model
    assert rc.calibrate("ewma-v1", 0.8, None, CURVES) == 0.8        # minutes unknown


def test_the_saved_curves_cover_every_live_model_and_role_and_never_reorder_chances():
    curves = json.loads(rc.CURVES_PATH.read_text(encoding="utf-8"))
    assert set(curves) >= {"ewma-v1", "minutes-v1", "context-v1", "context-v2"}
    for version, roles in curves.items():
        assert set(roles) == set(rc.ROLE_NAMES), version
        for role, curve in roles.items():
            ys = curve["y"]
            assert all(b >= a for a, b in zip(ys, ys[1:])), (version, role)   # monotone
            assert 0.0 <= min(ys) and max(ys) <= 1.0


def test_the_saved_bench_curves_pull_the_older_models_locks_down():
    # the finding the curves exist for: the old models' 85% for a bench player is too high
    for version in ("ewma-v1", "minutes-v1", "context-v1"):
        assert rc.calibrate(version, 0.85, 12) < 0.80, version


DAY = "2026-11-04"


def ledger_rows(model_p_over=0.8, player_id=1):
    base = {c: None for c in nba_paper.COLUMNS}
    return pd.DataFrame([base | {
        "game_date": DAY, "event_id": "e1", "home": "Detroit Pistons", "away": "Philadelphia 76ers",
        "player": "Bench Guy", "player_id": player_id, "line": 5.5, "over_odds": -300,
        "under_odds": 240, "model_version": "ewma-v1", "model_p_over": model_p_over,
        "fair_p_over": 0.72, "stat": "points", "book": "fanduel"}], columns=nba_paper.COLUMNS)


NO_ALT = pd.DataFrame(columns=nba_alt.COLUMNS)


def test_a_bench_players_leg_is_priced_with_the_corrected_chance_and_its_under_follows():
    legs = nba_parlay.candidate_legs(ledger_rows(), NO_ALT, DAY, "ewma-v1",
                                     minutes={1: 12.0}, curves=CURVES).set_index("Side")
    assert legs.loc["Over", "Model %"] == pytest.approx(70.0)       # 0.8 bent to 0.70
    assert legs.loc["Under", "Model %"] == pytest.approx(30.0)      # and the under is the rest
    # the leg's chance blends 30% corrected model with 70% market: 0.3*0.70 + 0.7*0.72
    assert legs.loc["Over", "prob"] == pytest.approx(0.3 * 0.70 + 0.7 * 0.72)


def test_without_minutes_or_for_other_stats_the_raw_chance_is_kept():
    raw = nba_parlay.candidate_legs(ledger_rows(), NO_ALT, DAY, "ewma-v1", curves=CURVES)
    assert raw.set_index("Side").loc["Over", "Model %"] == pytest.approx(80.0)
    rebounds = ledger_rows().assign(stat="rebounds")
    other = nba_parlay.candidate_legs(rebounds, NO_ALT, DAY, "ewma-v1", "rebounds",
                                      minutes={1: 12.0}, curves=CURVES)
    assert other.set_index("Side").loc["Over", "Model %"] == pytest.approx(80.0)
