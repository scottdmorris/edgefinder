import pytest

from edgefinder.models.elo import EloModel, GameResult


def test_equal_teams_home_edge():
    model = EloModel(home_advantage=24.0)
    prob = model.expected_home_win_prob("A", "B")
    assert 0.5 < prob < 0.56


def test_winner_gains_loser_drops():
    model = EloModel(k=4.0)
    model.update(GameResult("A", "B", 5, 3))
    assert model.rating("A") > 1500.0
    assert model.rating("B") < 1500.0


def test_ratings_are_zero_sum():
    model = EloModel(k=4.0)
    games = [
        GameResult("A", "B", 5, 3),
        GameResult("B", "C", 2, 7),
        GameResult("C", "A", 1, 0),
    ]
    model.train(games)
    total = sum(model.rating(t) for t in ("A", "B", "C"))
    assert total == pytest.approx(4500.0)


def test_better_team_favored_on_road():
    model = EloModel(k=20.0, home_advantage=24.0)
    for _ in range(30):
        model.update(GameResult("Strong", "Weak", 10, 1))
    # Strong should now be favored even as the away team
    assert model.expected_home_win_prob("Weak", "Strong") < 0.5


def test_update_does_not_mutate_shared_dict():
    model = EloModel()
    before = model.ratings
    model.update(GameResult("A", "B", 3, 2))
    assert before is not model.ratings
