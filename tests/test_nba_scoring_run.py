"""The scoring run a team is on right now."""

from edgefinder.data.nba_live import Play
from edgefinder.tracking import nba_game_view as view


def play(order, period, clock, away, home):
    return Play(order=order, period=period, clock=clock, team="", text="basket", score="",
                away_score=away, home_score=home)


def test_a_team_outscoring_the_other_heavily_is_on_a_run():
    plays = [play(1, "Q3", "8:00", 60, 60), play(2, "Q3", "7:30", 62, 60), play(3, "Q3", "7:00", 62, 62),
             play(4, "Q3", "6:30", 65, 62), play(5, "Q3", "6:00", 68, 62), play(6, "Q3", "5:30", 71, 62)]
    assert view.scoring_run(plays, "ORL", "UTA") == "ORL on a 9-0 run"


def test_the_longest_lopsided_stretch_is_reported_including_the_few_points_given_up():
    plays = [play(1, "Q3", "8:00", 60, 60), play(2, "Q3", "7:30", 60, 63), play(3, "Q3", "7:00", 62, 63),
             play(4, "Q3", "6:30", 62, 66), play(5, "Q3", "6:00", 62, 69), play(6, "Q3", "5:30", 62, 72)]
    assert view.scoring_run(plays, "ORL", "UTA") == "UTA on a 12-2 run"


def test_an_even_stretch_or_a_short_burst_is_not_a_run():
    even = [play(n, "Q1", "6:00", 2 * n, 2 * n) for n in range(1, 8)]
    assert view.scoring_run(even, "ORL", "UTA") == ""
    burst = [play(1, "Q1", "6:00", 10, 10), play(2, "Q1", "5:30", 13, 10), play(3, "Q1", "5:00", 15, 10)]
    assert view.scoring_run(burst, "ORL", "UTA") == ""
    assert view.scoring_run([], "ORL", "UTA") == ""
