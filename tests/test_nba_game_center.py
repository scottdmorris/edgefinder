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


def shot(team, x, y, made=True):
    from edgefinder.data.nba_live import Shot
    return Shot(team=team, player=f"{team} shooter", made=made, x=x, y=y, period=1,
                distance=12.0, is_three=False, description="")


def test_the_court_draws_both_teams_shots_on_the_home_floor_with_labels_at_each_end(monkeypatch):
    monkeypatch.setattr(center.st, "session_state", {})
    shots = [shot("MIA", 10, 50), shot("MIA", 20, 40, made=False), shot("GSW", 90, 50)]
    html = center.court(GAME, shots, shots, ("#98002E", "#FFC72C"))
    assert html.startswith('<div class="bk-court"><svg viewBox="0 0 940 500"')
    assert html.count("<circle") == 2 and html.count("<line") == 2          # 2 makes, 1 miss (x)
    assert 'fill="#98002E"' in html and 'fill="#FFC72C"' in html           # each team's color
    assert "MIA shooter · missed · 12 ft · Q1" in html                      # the tap/hover detail
    assert "fresh" not in html                                              # first look: no pops


def test_shots_that_arrive_after_the_first_look_pop_in(monkeypatch):
    state = {}
    monkeypatch.setattr(center.st, "session_state", state)
    first = [shot("MIA", 10, 50)]
    center.court(GAME, first, first, ("#98002E", "#FFC72C"))
    later = first + [shot("GSW", 90, 50)]
    html = center.court(GAME, later, later, ("#98002E", "#FFC72C"))
    assert html.count("bk-shot fresh") == 1


def test_the_paint_and_center_circle_take_the_home_teams_color():
    from edgefinder.ui import style
    from edgefinder.tracking import nba_game_view as view
    lines = {n: list(zip(g["x"], g["y"])) for n, g in view.court_lines().groupby("line")}
    html = style.court_svg(lines, [], team_colors.team_color("GSW"), "logo.svg")
    tint = team_colors.rgba(team_colors.team_color("GSW"), 0.32)
    assert html.count(f'fill="{tint}"') == 2                                 # both paints
    assert 'href="logo.svg"' in html and html.count("<polyline") == len(lines)


def test_the_court_escapes_what_it_shows_and_ignores_bad_colors():
    from edgefinder.ui import style
    html = style.court_svg({}, [{"x": 5, "y": 5, "made": True, "color": "red;x", "label": "<b>"}],
                           "not a color", labels={"left": ("<i>", "#FFFFFF")})
    assert "<b>" not in html and "<i>" not in html and "red;x" not in html


def test_each_team_is_drawn_at_its_own_end_and_second_half_shots_are_turned_around():
    from edgefinder.tracking import nba_game_view as view
    placed = view.to_ends([shot("MIA", 10, 30), shot("MIA", 90, 30), shot("GSW", 85, 40),
                           shot("GSW", 20, 40)], "MIA", "GSW")
    assert [(s.x, s.y) for s in placed] == [(10, 30), (10, 70), (85, 40), (80, 60)]
    assert all(s.x <= 50 for s in placed if s.team == "MIA")
    assert all(s.x >= 50 for s in placed if s.team == "GSW")


def test_the_team_tag_is_real_bold_text_not_markdown_stars():
    assert "<b>MIA</b>" in center._team_tag("MIA", "#98002E") and "**" not in center._team_tag(
        "MIA", "#98002E")
