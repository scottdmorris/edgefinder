import pytest

from edgefinder import pipeline
from edgefinder.betting import odds_math
from edgefinder.betting.suggest import CandidateLeg, suggest_parlays


def _row(with_sharp=True):
    row = {
        "p_home": 0.55, "p_away": 0.45, "model_total": 8.5,
        "home_ml": 110, "away_ml": -130,
        "total_line": 8.5, "over_odds": -110, "under_odds": -110,
    }
    if with_sharp:
        # Pinnacle prices home much stronger than FanDuel does
        row.update({
            "sharp_home_ml": -120, "sharp_away_ml": 100,
            "sharp_total_line": 8.5,
            "sharp_over_odds": -105, "sharp_under_odds": -115,
        })
    return row


def test_anchor_prefers_pinnacle():
    row = _row(with_sharp=True)
    pipeline._attach_ev(row)
    assert row["anchor"] == "pinnacle"


def test_anchor_falls_back_to_fanduel():
    row = _row(with_sharp=False)
    pipeline._attach_ev(row)
    assert row["anchor"] == "fanduel"
    assert row["sharp_best_ev"] is None


def test_sharp_ev_is_pinnacle_vs_fanduel_price():
    row = _row(with_sharp=True)
    pipeline._attach_ev(row)
    sharp_home, _ = odds_math.devig_two_way(
        odds_math.implied_prob(-120), odds_math.implied_prob(100))
    expected = sharp_home * odds_math.american_to_decimal(110) - 1.0
    assert row["sharp_home_ev"] == pytest.approx(expected)
    # FanDuel +110 on a side Pinnacle rates ~52%: clearly +EV
    assert row["sharp_home_ev"] > 0.05


def test_blend_anchors_to_sharp_probability():
    row = _row(with_sharp=True)
    pipeline._attach_ev(row)
    sharp_home, _ = odds_math.devig_two_way(
        odds_math.implied_prob(-120), odds_math.implied_prob(100))
    expected = 0.3 * 0.55 + 0.7 * sharp_home
    assert row["p_home_bet"] == pytest.approx(expected)


def test_sharp_total_ignored_when_line_differs():
    row = _row(with_sharp=True)
    row["sharp_total_line"] = 8.0  # different line: not comparable
    pipeline._attach_ev(row)
    assert "sharp_over_ev" not in row


def test_diversity_caps_leg_reuse():
    # one dominant leg plus several mediocre ones
    legs = [
        CandidateLeg("g1", "star leg", 0.62, 100, 0.24),
        CandidateLeg("g2", "leg b", 0.55, 100, 0.10),
        CandidateLeg("g3", "leg c", 0.55, 100, 0.10),
        CandidateLeg("g4", "leg d", 0.54, 100, 0.08),
        CandidateLeg("g5", "leg e", 0.54, 100, 0.08),
    ]
    suggestions = suggest_parlays(legs, num_legs=2, top_n=5)
    star_count = sum(
        1 for s in suggestions for leg in s.legs if leg.description == "star leg")
    assert star_count <= 2
    assert len(suggestions) >= 3  # still returns a varied slate
