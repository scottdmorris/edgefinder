import pytest

from edgefinder.models import soccer


def _sample_matches():
    # Strong beats Weak home and away; Mid splits
    return [
        soccer.Match("Strong", "Weak", 3, 0),
        soccer.Match("Weak", "Strong", 0, 2),
        soccer.Match("Strong", "Mid", 2, 1),
        soccer.Match("Mid", "Strong", 1, 1),
        soccer.Match("Mid", "Weak", 2, 0),
        soccer.Match("Weak", "Mid", 1, 2),
    ]


def test_fit_league_requires_enough_matches():
    with pytest.raises(ValueError):
        soccer.fit_league(_sample_matches()[:2])


def test_strong_team_has_higher_attack():
    model = soccer.fit_league(_sample_matches())
    assert model.attack["Strong"] > model.attack["Weak"]
    assert model.defense["Strong"] < model.defense["Weak"]


def test_match_probs_sum_to_one():
    probs = soccer.match_probs(1.5, 1.1)
    assert probs["home"] + probs["draw"] + probs["away"] == pytest.approx(1.0)


def test_stronger_home_rate_favors_home():
    favored = soccer.match_probs(2.2, 0.8)
    assert favored["home"] > favored["away"]
    assert favored["home"] > 0.5


def test_even_low_scoring_match_has_high_draw_prob():
    probs = soccer.match_probs(1.0, 1.0)
    assert probs["draw"] > 0.2


def test_expected_goals_uses_ratings():
    model = soccer.fit_league(_sample_matches())
    strong_home, weak_away = soccer.expected_goals(model, "Strong", "Weak")
    weak_home, strong_away = soccer.expected_goals(model, "Weak", "Strong")
    assert strong_home > weak_home
    assert strong_away > weak_away


def test_unknown_team_gets_neutral_rating():
    model = soccer.fit_league(_sample_matches())
    home_rate, away_rate = soccer.expected_goals(model, "Newcomer", "Mid")
    assert home_rate > 0
    assert away_rate > 0


def test_total_goals_probs():
    probs = soccer.total_goals_probs(1.5, 1.2, 2.5)
    assert probs["over"] + probs["under"] == pytest.approx(1.0)
