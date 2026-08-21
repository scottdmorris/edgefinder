import pytest

from edgefinder import pipeline


def _row_with_market():
    return {
        "p_home": 0.60, "p_away": 0.40, "model_total": 8.5,
        "home_ml": 100, "away_ml": -120,  # devig fair_home ~0.478
        "total_line": 8.5, "over_odds": -110, "under_odds": -110,
    }


def test_betting_prob_is_market_anchored():
    row = _row_with_market()
    pipeline._attach_ev(row)
    fair_home = 0.5 / (0.5 + 1 / (1 + 100 / 120))
    expected = 0.3 * 0.60 + 0.7 * fair_home
    assert row["p_home_bet"] == pytest.approx(expected, abs=1e-6)
    assert row["p_home_bet"] < row["p_home"]  # shrunk toward market


def test_ev_uses_blended_probability():
    row = _row_with_market()
    pipeline._attach_ev(row)
    # home ML at +100 (decimal 2.0): EV = 2*p_bet - 1
    assert row["home_ml_ev"] == pytest.approx(2.0 * row["p_home_bet"] - 1.0)


def test_moderate_disagreement_not_suspect():
    row = _row_with_market()
    pipeline._attach_ev(row)
    assert row["suspect"] is False


def test_extreme_disagreement_is_suspect():
    row = _row_with_market()
    row["p_home"], row["p_away"] = 0.85, 0.15
    pipeline._attach_ev(row)
    assert row["suspect"] is True


def test_no_market_odds_leaves_no_blend():
    row = {"p_home": 0.60, "p_away": 0.40, "model_total": 8.5}
    pipeline._attach_ev(row)
    assert "p_home_bet" not in row
    assert row["best_ev"] is None
