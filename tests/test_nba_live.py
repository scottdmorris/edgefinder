import pytest

from edgefinder.data import nba_live

SCOREBOARD = {"scoreboard": {"games": [
    {"gameId": "0022600173", "gameStatus": 2, "gameStatusText": "2nd Qtr             ",
     "period": 2, "gameClock": "PT01M25.00S",
     "awayTeam": {"teamTricode": "PHI", "score": 43},
     "homeTeam": {"teamTricode": "DET", "score": 41}},
    {"gameId": "0022600178", "gameStatus": 1, "gameStatusText": "8:00 pm ET",
     "period": 0, "gameClock": "",
     "awayTeam": {"teamTricode": "IND", "score": 0},
     "homeTeam": {"teamTricode": "MEM", "score": 0}},
]}}


def player(pid, name, points, rebounds, assists, minutes, played="1", oncourt="0"):
    return {"personId": pid, "name": name, "played": played, "oncourt": oncourt,
            "statistics": {"points": points, "reboundsTotal": rebounds,
                           "assists": assists, "minutes": minutes}}


BOX = {"game": {
    "awayTeam": {"teamTricode": "PHI", "players": [
        player(1, "Tyrese Maxey", 18, 3, 4, "PT20M30.00S", oncourt="1")]},
    "homeTeam": {"teamTricode": "DET", "players": [
        player(2, "Cade Cunningham", 4, 4, 3, "PT14M57.00S"),
        player(3, "Bench Guy", 0, 0, 0, "", played="0")]},
}}


DETAILED_BOX = {"game": {
    "period": 2,
    "awayTeam": {
        "teamTricode": "PHI",
        "periods": [{"period": 1, "score": 30}, {"period": 2, "score": 12},
                    {"period": 3, "score": 0}, {"period": 4, "score": 0}],
        "statistics": {"fieldGoalsMade": 15, "fieldGoalsAttempted": 27, "assists": 10,
                       "pointsInThePaint": 12, "pointsFastBreak": 4, "benchPoints": 8,
                       "turnovers": 7, "notAStatWeKeep": 99},
        "players": [{
            "personId": 1, "name": "Tyrese Maxey", "played": "1", "oncourt": "1",
            "starter": "1",
            "statistics": {"points": 18, "reboundsTotal": 3, "assists": 4,
                           "minutes": "PT20M30.00S", "fieldGoalsMade": 7,
                           "fieldGoalsAttempted": 12, "threePointersMade": 3,
                           "threePointersAttempted": 6, "freeThrowsMade": 1,
                           "freeThrowsAttempted": 2, "steals": 1, "blocks": 0,
                           "turnovers": 2, "plusMinusPoints": 5.0}}]},
    "homeTeam": {
        "teamTricode": "DET",
        "periods": [{"period": 1, "score": 28}, {"period": 2, "score": 9},
                    {"period": 3, "score": 0}, {"period": 4, "score": 0}],
        "statistics": {"fieldGoalsMade": 14, "fieldGoalsAttempted": 26},
        "players": []},
}}


def test_a_player_line_carries_the_full_shooting_split_and_role():
    maxey = nba_live.parse_boxscore(DETAILED_BOX)[1]
    assert maxey.starter is True
    assert (maxey.fg_made, maxey.fg_att) == (7, 12)
    assert (maxey.threes, maxey.three_att) == (3, 6)
    assert (maxey.ft_made, maxey.ft_att) == (1, 2)
    assert (maxey.steals, maxey.blocks, maxey.turnovers, maxey.plus_minus) == (1, 0, 2, 5.0)


def test_a_player_line_without_the_extra_stats_falls_back_to_zeros():
    simple = nba_live.parse_boxscore(BOX)[1]
    assert simple.fg_made == 0 and simple.starter is False and simple.plus_minus == 0.0


def test_team_stats_keep_only_the_numbers_we_compare():
    stats = nba_live.parse_team_stats(DETAILED_BOX)
    assert stats["PHI"]["fieldGoalsMade"] == 15 and stats["PHI"]["pointsInThePaint"] == 12
    assert "notAStatWeKeep" not in stats["PHI"]
    assert stats["DET"] == {"fieldGoalsMade": 14.0, "fieldGoalsAttempted": 26.0}


def test_period_scores_cover_only_the_periods_played_so_far():
    assert nba_live.parse_period_scores(DETAILED_BOX) == {"PHI": [30, 12], "DET": [28, 9]}


def test_no_box_score_means_no_team_stats_or_period_scores():
    assert nba_live.parse_team_stats({}) == {}
    assert nba_live.parse_period_scores({}) == {}


SHOT_PLAYS = {"game": {"actions": [
    {"isFieldGoal": 1, "teamTricode": "PHI", "playerNameI": "J. Embiid", "shotResult": "Made",
     "x": 8.1, "y": 52.6, "period": 1, "shotDistance": 2.7, "actionType": "2pt",
     "description": "Embiid Layup"},
    {"isFieldGoal": 1, "teamTricode": "DET", "playerNameI": "D. Robinson",
     "shotResult": "Missed", "x": 81.1, "y": 7.7, "period": 2, "shotDistance": 24.5,
     "actionType": "3pt", "description": "MISS Robinson 3PT"},
    {"isFieldGoal": 1, "teamTricode": "PHI", "shotResult": "Made", "x": None, "y": None},
    {"isFieldGoal": 0, "actionType": "rebound", "description": "REBOUND"},
]}}


def test_shots_have_their_location_result_and_shooter():
    layup, three = nba_live.parse_shots(SHOT_PLAYS)
    assert (layup.team, layup.player, layup.made, layup.is_three) == \
        ("PHI", "J. Embiid", True, False)
    assert (layup.x, layup.y, layup.period, layup.distance) == (8.1, 52.6, 1, 2.7)
    assert (three.made, three.is_three, three.period) == (False, True, 2)


def test_shots_without_a_location_and_non_shots_are_left_out():
    assert len(nba_live.parse_shots(SHOT_PLAYS)) == 2
    assert nba_live.parse_shots({}) == []


def test_the_scoreboard_reads_timeouts_and_bonus_for_the_header():
    payload = {"scoreboard": {"games": [{
        "gameId": "g", "gameStatus": 2, "gameStatusText": "Q2", "period": 2, "gameClock": "",
        "awayTeam": {"teamTricode": "A", "score": 1, "timeoutsRemaining": 3, "inBonus": "1"},
        "homeTeam": {"teamTricode": "B", "score": 2, "timeoutsRemaining": 5, "inBonus": None}}]}}
    game = nba_live.parse_scoreboard(payload)[0]
    assert (game.away_timeouts, game.home_timeouts) == (3, 5)
    assert game.away_bonus is True and game.home_bonus is False


def test_a_scoreboard_without_timeout_data_defaults_to_none_left():
    game = nba_live.parse_scoreboard(SCOREBOARD)[0]
    assert (game.away_timeouts, game.home_timeouts) == (0, 0)
    assert game.away_bonus is False


def test_durations_become_minutes_and_a_game_clock():
    assert nba_live.minutes_from_duration("PT13M51.00S") == pytest.approx(13.85)
    assert nba_live.minutes_from_duration("PT00M30.00S") == pytest.approx(0.5)
    assert nba_live.minutes_from_duration("") == 0.0
    assert nba_live.minutes_from_duration("garbage") == 0.0
    assert nba_live.clock_from_duration("PT01M25.00S") == "1:25"
    assert nba_live.clock_from_duration("PT00M07.40S") == "0:07"
    assert nba_live.clock_from_duration("") == ""


def test_the_scoreboard_lists_each_game_with_status_and_score():
    live, upcoming = nba_live.parse_scoreboard(SCOREBOARD)
    assert (live.away, live.home, live.away_score, live.home_score) == ("PHI", "DET", 43, 41)
    assert live.status == nba_live.LIVE and live.status_text == "2nd Qtr"
    assert live.period == 2 and live.clock == "1:25"
    assert upcoming.status == nba_live.SCHEDULED and upcoming.clock == ""


def test_an_empty_scoreboard_is_no_games():
    assert nba_live.parse_scoreboard({}) == []
    assert nba_live.parse_scoreboard({"scoreboard": {"games": []}}) == []


def test_the_box_score_is_keyed_by_player_id_across_both_teams():
    box = nba_live.parse_boxscore(BOX)
    assert set(box) == {1, 2, 3}
    maxey = box[1]
    assert (maxey.name, maxey.team, maxey.points, maxey.rebounds, maxey.assists) == \
        ("Tyrese Maxey", "PHI", 18, 3, 4)
    assert maxey.minutes == pytest.approx(20.5) and maxey.on_court and maxey.played


def test_a_player_who_has_not_played_is_marked_so():
    bench = nba_live.parse_boxscore(BOX)[3]
    assert not bench.played and bench.minutes == 0.0


def test_a_missing_box_score_is_empty():
    assert nba_live.parse_boxscore({}) == {}


PLAYS = {"game": {"actions": [
    {"orderNumber": 30, "period": 2, "clock": "PT04M35.00S", "teamTricode": "PHI",
     "description": "Maxey 3PT Jump Shot (18 PTS)", "scoreAway": "45", "scoreHome": "41"},
    {"orderNumber": 10, "period": 1, "clock": "PT11M20.00S", "teamTricode": "DET",
     "description": "Cunningham 2PT Layup", "scoreAway": "0", "scoreHome": "2"},
    {"orderNumber": 20, "period": 1, "clock": "PT00M00.00S", "teamTricode": None,
     "description": "Period End", "scoreAway": "20", "scoreHome": "22"},
    {"orderNumber": 25, "period": 2, "clock": "PT05M00.00S", "teamTricode": "DET",
     "description": "   ", "scoreAway": "45", "scoreHome": "41"},
    {"orderNumber": 99, "period": 5, "clock": "PT02M10.00S", "teamTricode": "DET",
     "description": "Free throw", "scoreAway": "110", "scoreHome": "111"},
]}}


def test_plays_come_back_in_game_order_and_blank_ones_are_dropped():
    plays = nba_live.parse_playbyplay(PLAYS, "PHI", "DET")
    assert [p.order for p in plays] == [10, 20, 30, 99]
    first = plays[0]
    assert (first.period, first.clock, first.team) == ("Q1", "11:20", "DET")
    assert first.score == "PHI 0 - DET 2"


def test_each_play_carries_the_score_as_numbers_too():
    first = nba_live.parse_playbyplay(PLAYS, "PHI", "DET")[0]
    assert (first.away_score, first.home_score) == (0, 2)
    assert nba_live.parse_playbyplay(PLAYS, "PHI", "DET")[2].away_score == 45


def test_a_period_is_worded_the_way_the_scoreboard_words_it():
    assert nba_live.period_status("Q1") == "1st Qtr"
    assert nba_live.period_status("Q3") == "3rd Qtr"
    assert nba_live.period_status("OT1") == "OT1"


def test_a_missing_score_counts_as_zero():
    bare = {"game": {"actions": [{"orderNumber": 1, "period": 1, "description": "Jump Ball",
                                  "scoreAway": None}]}}
    play = nba_live.parse_playbyplay(bare, "A", "B")[0]
    assert (play.away_score, play.home_score) == (0, 0)


def test_a_neutral_play_has_no_team_and_overtime_periods_are_labelled():
    plays = nba_live.parse_playbyplay(PLAYS, "PHI", "DET")
    assert plays[1].team == "" and plays[1].text == "Period End"
    assert plays[-1].period == "OT1"
    assert nba_live.period_label(4) == "Q4" and nba_live.period_label(6) == "OT2"


def test_an_empty_play_by_play_is_no_plays():
    assert nba_live.parse_playbyplay({}, "PHI", "DET") == []


def test_every_team_has_a_logo_and_an_unknown_one_has_none():
    assert nba_live.logo_url("BOS").startswith("https://cdn.nba.com/logos/nba/161061273")
    assert nba_live.logo_url("BOS").endswith("/global/L/logo.svg")
    assert nba_live.logo_url("ZZZ") == ""
    assert len(nba_live.team_ids()) == 30


def test_a_failed_fetch_becomes_one_clear_error(monkeypatch):
    from nba_api.live.nba.endpoints import scoreboard

    def boom(*args, **kwargs):
        raise ConnectionError("secret details that should not leak")

    monkeypatch.setattr(scoreboard, "ScoreBoard", boom)
    with pytest.raises(nba_live.LiveDataError) as error:
        nba_live.fetch_games()
    assert "ConnectionError" in str(error.value)
    assert "secret details" not in str(error.value)
