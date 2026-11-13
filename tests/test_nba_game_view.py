
import pytest

from edgefinder.data.nba_live import PlayerLine, Shot
from edgefinder.tracking import nba_game_view as view


def shot(team="PHI", made=True, period=1, three=False, x=20.0, y=50.0, player="A. Player"):
    return Shot(team=team, player=player, made=made, x=x, y=y, period=period,
                distance=10.0, is_three=three, description="a shot")


def line(pid, team, points=0, rebounds=0, assists=0, starter=True, played=True, minutes=20.0,
         on_court=False):
    return PlayerLine(player_id=pid, name=f"P{pid}", team=team, points=points,
                      rebounds=rebounds, assists=assists, minutes=minutes, played=played,
                      on_court=on_court, starter=starter, fg_made=points // 2, fg_att=points,
                      threes=1, three_att=2, ft_made=1, ft_att=2, plus_minus=3.0)


# ---- the court --------------------------------------------------------------------

def test_the_court_fits_inside_the_0_to_100_square_the_shots_use():
    court = view.court_lines()
    assert court["x"].between(0, 100).all() and court["y"].between(0, 100).all()
    assert court["x"].min() == 0 and court["x"].max() == pytest.approx(100)
    assert court["y"].min() == 0 and court["y"].max() == pytest.approx(100)


def test_the_court_has_both_ends_marked_the_same_way():
    names = set(view.court_lines()["line"])
    for part in ("paint", "free throw circle", "three point line", "restricted area",
                 "backboard", "hoop"):
        assert f"left {part}" in names and f"right {part}" in names
    assert {"boundary", "half court", "center circle"} <= names


def test_the_two_ends_are_mirror_images():
    court = view.court_lines()
    left = court[court["line"] == "left three point line"].sort_values("order")
    right = court[court["line"] == "right three point line"].sort_values("order")
    assert left["x"].to_numpy() + right["x"].to_numpy() == pytest.approx(100.0)
    assert left["y"].to_numpy() == pytest.approx(right["y"].to_numpy())


def test_every_point_on_the_three_point_arc_is_the_right_distance_from_the_hoop():
    court = view.court_lines()
    arc = court[court["line"] == "left three point line"].sort_values("order").iloc[2:-2]
    feet_x = arc["x"] / 100 * view.COURT_LENGTH
    feet_y = arc["y"] / 100 * view.COURT_WIDTH
    distance = ((feet_x - view.HOOP_X) ** 2 + (feet_y - view.HOOP_Y) ** 2) ** 0.5
    assert distance.between(23.0, 24.5).all()      # 23.75 ft, less the straight corner ends


def test_the_hoop_sits_where_a_real_one_does():
    hoop = view.court_lines().query("line == 'left hoop'")
    assert hoop["x"].mean() == pytest.approx(view.HOOP_X / view.COURT_LENGTH * 100, abs=0.1)
    assert hoop["y"].mean() == pytest.approx(50.0, abs=0.1)


# ---- shots ------------------------------------------------------------------------

def test_shots_can_be_limited_to_one_period():
    shots = [shot(period=1), shot(period=2), shot(period=2)]
    assert len(view.shots_in_period(shots, None)) == 3
    assert len(view.shots_in_period(shots, 2)) == 2
    assert view.shots_in_period(shots, 4) == []


def test_a_teams_shooting_summary_counts_makes_attempts_and_threes():
    shots = [shot(made=True), shot(made=False), shot(made=True, three=True),
             shot(made=False, three=True), shot(team="DET", made=True)]
    summary = view.shot_summary(shots, "PHI")
    assert (summary["made"], summary["attempts"]) == (2, 4)
    assert summary["pct"] == pytest.approx(50.0)
    assert (summary["threes_made"], summary["threes_attempts"]) == (1, 2)


def test_a_team_with_no_shots_has_a_zero_percentage_not_an_error():
    assert view.shot_summary([], "PHI")["pct"] == 0.0


def test_the_shot_table_labels_each_result():
    table = view.shot_table([shot(made=True), shot(made=False)])
    assert list(table["Result"]) == ["Made", "Missed"]
    assert {"x", "y", "Team", "Player", "Distance (ft)", "Period"} <= set(table.columns)


# ---- team comparison --------------------------------------------------------------

AWAY = {"fieldGoalsMade": 15, "fieldGoalsAttempted": 27, "threePointersMade": 8,
        "threePointersAttempted": 16, "freeThrowsMade": 3, "freeThrowsAttempted": 4,
        "reboundsTotal": 13, "assists": 10, "turnovers": 7, "pointsInThePaint": 12}
HOME = {"fieldGoalsMade": 14, "fieldGoalsAttempted": 26, "threePointersMade": 6,
        "threePointersAttempted": 11, "freeThrowsMade": 3, "freeThrowsAttempted": 3,
        "reboundsTotal": 13, "assists": 10, "turnovers": 8, "pointsInThePaint": 14}


def by_label(rows):
    return {row["label"]: row for row in rows}


def test_shooting_rows_show_the_percentage_and_the_makes_and_attempts():
    rows = by_label(view.comparison_rows(AWAY, HOME))
    assert rows["Field goals"]["away_text"] == "55.6% (15/27)"
    assert rows["Field goals"]["home_text"] == "53.8% (14/26)"
    assert rows["Free throws"]["home_text"] == "100.0% (3/3)"


def test_the_team_ahead_is_named_and_a_tie_is_not():
    rows = by_label(view.comparison_rows(AWAY, HOME))
    assert rows["Field goals"]["ahead"] == "away"
    assert rows["Points in the paint"]["ahead"] == "home"
    assert rows["Rebounds"]["ahead"] == ""


def test_for_turnovers_fewer_is_ahead():
    rows = by_label(view.comparison_rows(AWAY, HOME))
    assert rows["Turnovers"]["ahead"] == "away"        # 7 against 8


def test_bar_shares_split_the_pair_and_a_zero_zero_row_is_even():
    rows = by_label(view.comparison_rows(AWAY, HOME))
    assert rows["Rebounds"]["away_share"] == pytest.approx(0.5)
    assert rows["Points in the paint"]["away_share"] == pytest.approx(12 / 26)
    zero = by_label(view.comparison_rows({"assists": 0}, {"assists": 0}))
    assert zero["Assists"]["away_share"] == 0.5


def test_a_stat_one_team_lacks_is_skipped_not_shown_as_zero():
    rows = by_label(view.comparison_rows({"assists": 5}, {"rebounds": 5}))
    assert rows == {}
    assert "Assists" in by_label(view.comparison_rows({"assists": 5}, {"assists": 3}))


# ---- leaders, quarters, box -------------------------------------------------------

def test_leaders_are_each_teams_best_in_the_three_main_stats():
    players = {1: line(1, "PHI", points=20, rebounds=3, assists=9),
               2: line(2, "PHI", points=11, rebounds=12, assists=2),
               3: line(3, "DET", points=30), 4: line(4, "PHI", points=99, played=False)}
    top = view.leaders(players, "PHI")
    assert (top["Points"].player_id, top["Rebounds"].player_id, top["Assists"].player_id) == \
        (1, 2, 1)                                    # the player who never played is ignored
    assert view.leaders({}, "PHI") == {"Points": None, "Rebounds": None, "Assists": None}


def test_the_quarter_table_has_a_column_per_period_and_a_total():
    table = view.quarter_table({"PHI": [30, 12], "DET": [28, 9]}, "PHI", "DET", 42, 37)
    assert list(table.columns) == ["Q1", "Q2", "Total"]
    assert list(table.loc["PHI"]) == [30, 12, 42]
    assert list(table.loc["DET"]) == [28, 9, 37]


def test_overtime_periods_are_labelled_and_a_missing_team_is_zeros():
    table = view.quarter_table({"PHI": [20, 20, 20, 20, 8]}, "PHI", "DET", 88, 80)
    assert list(table.columns)[-2:] == ["OT1", "Total"]
    assert list(table.loc["DET"])[:2] == [0, 0]


def test_the_box_table_splits_starters_from_bench_and_sorts_by_points():
    players = {1: line(1, "PHI", points=10), 2: line(2, "PHI", points=25),
               3: line(3, "PHI", points=8, starter=False),
               4: line(4, "PHI", points=0, starter=False, played=False),
               5: line(5, "DET", points=40)}
    starters = view.box_table(players, "PHI", starters=True)
    bench = view.box_table(players, "PHI", starters=False)
    assert list(starters["Pts"]) == [25, 10]
    assert list(bench["Pts"]) == [8]                  # the one who didn't play is left out
    assert starters["FG"].iloc[0] == "12-25" and starters["+/-"].iloc[0] == "+3"


def test_a_player_on_the_court_is_marked_in_the_box_table():
    players = {1: line(1, "PHI", points=10, on_court=True)}
    assert "🏀" in view.box_table(players, "PHI", True)["Player"].iloc[0]


# ---- score changes, for the pop on a basket ------------------------------------------------------

def test_score_deltas_report_what_each_team_scored_since_the_last_look():
    before = {"g1": (50, 48), "g2": (30, 30)}
    after = {"g1": (53, 48), "g2": (30, 32)}
    assert view.score_deltas(before, after) == {"g1": (3, 0), "g2": (0, 2)}


def test_both_teams_can_score_between_two_looks_and_an_unchanged_game_is_left_out():
    assert view.score_deltas({"g1": (10, 10), "g2": (5, 5)},
                             {"g1": (12, 13), "g2": (5, 5)}) == {"g1": (2, 3)}


def test_a_game_seen_for_the_first_time_does_not_pop():
    assert view.score_deltas({}, {"g1": (88, 91)}) == {}
    assert view.score_deltas({"g1": (88, 91)}, {"g1": (88, 91), "g2": (2, 0)}) == {}


def test_a_corrected_score_never_shows_a_negative_pop():
    assert view.score_deltas({"g1": (50, 50)}, {"g1": (49, 52)}) == {"g1": (0, 2)}
    assert view.score_deltas({"g1": (50, 50)}, {"g1": (49, 50)}) == {}


# ---- fouls ---------------------------------------------------------------------------------------------

def fouled(pid, team, fouls, played=True):
    return PlayerLine(player_id=pid, name=f"First Last{pid}", team=team, points=0, rebounds=0,
                      assists=0, minutes=10.0, played=played, on_court=False, fouls=fouls)


def test_foul_trouble_starts_at_four_fouls_for_players_who_played_most_fouls_first():
    players = {1: fouled(1, "GSW", 3), 2: fouled(2, "GSW", 4), 3: fouled(3, "GSW", 5),
               4: fouled(4, "GSW", 6), 5: fouled(5, "MIA", 5), 6: fouled(6, "GSW", 5, played=False)}
    assert view.foul_trouble(players, "GSW") == [
        ("First Last4", 6), ("First Last3", 5), ("First Last2", 4)]
    assert view.foul_trouble(players, "MIA") == [("First Last5", 5)]


def test_the_foul_line_shows_team_fouls_and_the_players_in_trouble_by_surname():
    players = {3: fouled(3, "GSW", 5), 2: fouled(2, "GSW", 4)}
    text = view.foul_line("GSW", {"GSW": {"foulsPersonal": 12.0}}, players)
    assert text == "GSW fouls 12 · foul trouble: Last3 5, Last2 4"


def test_the_foul_line_copes_with_a_missing_number_or_nobody_in_trouble():
    assert view.foul_line("GSW", {"GSW": {"foulsPersonal": 7.0}}, {}) == "GSW fouls 7"
    assert view.foul_line("GSW", {}, {3: fouled(3, "GSW", 4)}) == "GSW foul trouble: Last3 4"
    assert view.foul_line("GSW", {}, {}) == ""


def test_the_box_table_shows_each_players_fouls():
    players = {1: fouled(1, "PHI", 2), 2: fouled(2, "PHI", 5)}
    table = view.box_table(players, "PHI", starters=False)
    assert "PF" in table.columns and sorted(table["PF"]) == [2, 5]


# ---- the score strip -----------------------------------------------------------------------------------

def test_a_live_game_chip_shows_the_score_and_a_short_period_and_clock():
    assert view.chip_label("MIA", "GSW", 83, 98, "live", "4th Qtr", "8:34") == \
        "MIA 83-98 GSW · Q4 8:34"
    assert view.chip_label("MIA", "GSW", 50, 49, "live", "2nd Qtr", "0:12") == \
        "MIA 50-49 GSW · Q2 0:12"
    assert view.chip_label("MIA", "GSW", 101, 101, "live", "OT1", "3:00") == \
        "MIA 101-101 GSW · OT1 3:00"


def test_finished_and_upcoming_games_read_differently():
    assert view.chip_label("ORL", "PHX", 104, 117, "final", "Final") == "ORL 104-117 PHX · Final"
    assert view.chip_label("MIA", "GSW", 0, 0, "upcoming", "10:00 pm ET") == \
        "MIA @ GSW · 10:00 pm ET"


# ---- what changed since the last refresh, for the animations ------------------------------------------

def test_new_plays_are_the_ones_after_the_last_seen_and_a_first_look_marks_none():
    assert view.new_plays(None, [1, 2, 3]) == set()
    assert view.new_plays(2, [1, 2, 3, 4]) == {3, 4}
    assert view.new_plays(4, [1, 2, 3, 4]) == set()


def test_a_slip_leg_that_changed_status_is_flagged_once_and_a_new_leg_is_not():
    before = {"A · Over 9.5": "alive", "B · 10+": "alive"}
    now = {"A · Over 9.5": "hit", "B · 10+": "alive", "C · 5+": "alive"}
    assert view.changed_status(before, now) == {"A · Over 9.5"}
    assert view.changed_status(now, now) == set()
