import re

from edgefinder.data import nba_live
from edgefinder.data import team_colors


def test_every_team_has_a_color_and_nothing_extra():
    assert set(team_colors.COLORS) == set(nba_live.team_ids())


def test_every_color_is_a_valid_hex_value():
    assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", c) for c in team_colors.COLORS.values())


def test_every_color_is_bright_enough_to_read_on_the_dark_background():
    # perceived brightness, 0 (black) to 255 (white); the app background is near 11
    def brightness(color):
        red, green, blue = team_colors._rgb(color)
        return 0.299 * red + 0.587 * green + 0.114 * blue
    dark = {code: c for code, c in team_colors.COLORS.items() if brightness(c) < 70}
    assert dark == {}


def test_an_unknown_team_gets_the_app_blue():
    assert team_colors.team_color("ZZZ") == team_colors.DEFAULT
    assert team_colors.team_color("NYK") == "#F58426"


def test_two_different_looking_teams_keep_their_own_colors():
    assert team_colors.matchup_colors("PHI", "DET") == ("#2A8BDB", "#E21F3F")


def test_two_similar_looking_teams_get_told_apart():
    away, home = team_colors.matchup_colors("MIL", "BOS")          # two greens
    assert away != home and home == team_colors.WHITE
    away, home = team_colors.matchup_colors("CHI", "TOR")          # two reds
    assert home == team_colors.WHITE


def test_a_team_against_itself_still_gets_two_colors():
    away, home = team_colors.matchup_colors("NYK", "NYK")
    assert away != home


def test_a_tinted_background_is_a_translucent_version_of_the_color():
    assert team_colors.rgba("#1493FF", 0.15) == "rgba(20,147,255,0.15)"
