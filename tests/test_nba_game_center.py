import pandas as pd

from edgefinder.data.nba_live import GameDetail, LiveGame, PlayerLine
from edgefinder.ui import nba_game_center as center
from edgefinder.ui import team_colors

GAME = LiveGame(game_id="g1", status=2, status_text="2nd Qtr", period=2, clock="5:00",
                away="MIA", home="GSW", away_score=40, home_score=44)


def player(pid, team, fouls):
    return PlayerLine(player_id=pid, name=f"Test Name{pid}", team=team, points=0, rebounds=0,
                      assists=0, minutes=12.0, played=True, on_court=False, fouls=fouls)


def detail(**kwargs):
    base = dict(plays=[], shots=[], players={}, team_stats={}, period_scores={})
    return GameDetail(**(base | kwargs))


def test_the_home_teams_floor_is_their_color_at_a_low_strength_across_the_whole_court():
    wash, mark = center.court_floor("GSW")
    spec = wash.to_dict()
    expected = team_colors.rgba(team_colors.team_color("GSW"), center.FLOOR_TINT)
    assert spec["mark"]["color"] == expected
    rows = list(spec["datasets"].values())[0]
    assert rows == [{"x": 0, "x2": 100, "y": 0, "y2": 100}]


def test_the_home_logo_sits_at_center_court():
    _, mark = center.court_floor("GSW")
    spec = mark.to_dict()
    row = list(spec["datasets"].values())[0][0]
    assert (row["x"], row["y"]) == (50, 50)
    assert spec["mark"]["type"] in ("image", "text")


def test_a_team_with_no_logo_gets_its_name_in_big_faint_letters_instead(monkeypatch):
    monkeypatch.setattr(center.nba_live, "logo_url", lambda code: "")
    _, mark = center.court_floor("GSW")
    spec = mark.to_dict()
    assert spec["mark"]["type"] == "text"
    assert list(spec["datasets"].values())[0][0]["name"] == "GSW"


def test_the_whole_court_is_floor_then_lines_then_logo_then_shots():
    chart = center._court_chart([], GAME, ("#98002E", "#FFC72C"))
    assert len(chart.to_dict()["layer"]) == 5


def test_foul_lines_show_both_teams_one_per_line_and_skip_a_team_with_nothing():
    d = detail(team_stats={"GSW": {"foulsPersonal": 9.0}, "MIA": {"foulsPersonal": 11.0}},
               players={1: player(1, "MIA", 5), 2: player(2, "GSW", 2)})
    text = center.foul_lines(GAME, d)
    assert text == "MIA fouls 11 · foul trouble: Name1 5  \nGSW fouls 9"
    assert center.foul_lines(GAME, detail()) == ""
