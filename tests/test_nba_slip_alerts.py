"""Mid-game warnings for a slip: fouled out, ejected, or off the floor for a long stretch."""

from edgefinder.data import nba_live
from edgefinder.data.nba_live import LIVE, Exit, LiveGame, PlayerLine
from edgefinder.tracking.nba_slip_tracker import exit_alert, game_minutes


def _game(period=3, clock="6:00", status=LIVE):
    return LiveGame("1", status, "Q3", period, clock, "BOS", "NYK", 60, 58)


def _player(**changes):
    base = dict(player_id=7, name="Example", team="BOS", points=10, rebounds=2, assists=1,
                minutes=18.0, played=True, on_court=False, starter=True)
    return PlayerLine(**(base | changes))


def test_game_minutes_counts_regulation_and_overtime():
    assert game_minutes(1, 720) == 0
    assert game_minutes(3, 360) == 30
    assert game_minutes(5, 0) == 53


def test_six_fouls_is_fouled_out_and_two_technicals_or_an_ejection_is_ejected():
    assert exit_alert(_player(fouls=6), None, _game()) == "Fouled out"
    assert exit_alert(_player(technicals=2), None, _game()) == "Ejected"
    assert exit_alert(_player(), Exit(ejected=True), _game()) == "Ejected"


def test_a_starter_off_the_floor_for_ten_game_minutes_gets_a_warning():
    left_in_first = Exit(out_period=2, out_seconds_left=240)       # out with 4:00 left in Q2
    alert = exit_alert(_player(), left_in_first, _game(period=3, clock="6:00"))
    assert alert.startswith("Off the floor for the last 10 minutes")


def test_a_normal_rest_or_a_player_back_on_court_is_not_a_warning():
    resting = Exit(out_period=3, out_seconds_left=540)             # out three minutes ago
    assert exit_alert(_player(), resting, _game()) == ""
    assert exit_alert(_player(on_court=True), Exit(out_period=1, out_seconds_left=60), _game()) == ""
    bench = Exit(out_period=2, out_seconds_left=240)
    assert exit_alert(_player(starter=False), bench, _game()) == ""  # ten minutes is routine off the bench


def test_no_warning_before_a_player_plays_or_after_the_game():
    assert exit_alert(_player(played=False), None, _game()) == ""
    assert exit_alert(_player(fouls=6), None, _game(status=nba_live.FINAL)) == ""
    assert exit_alert(None, None, _game()) == ""


def test_a_player_the_feed_lists_as_out_is_reported_with_the_reason():
    assert exit_alert(_player(not_playing="Injury"), None, _game()) == "Listed out: Injury"


def test_exits_keep_the_last_unanswered_substitution_and_any_ejection():
    def sub(order, kind, person, period, clock):
        return {"orderNumber": order, "actionType": "substitution", "subType": kind,
                "personId": person, "period": period, "clock": clock}
    payload = {"game": {"actions": [
        sub(1, "out", 7, 1, "PT06M00.00S"), sub(2, "in", 7, 1, "PT02M00.00S"),
        sub(3, "out", 7, 2, "PT04M00.00S"),
        sub(4, "out", 8, 1, "PT05M00.00S"), sub(5, "in", 8, 2, "PT12M00.00S"),
        {"orderNumber": 6, "actionType": "ejection", "personId": 9, "period": 2},
        {"orderNumber": 7, "actionType": "period", "period": 2},
    ]}}
    exits = nba_live.parse_exits(payload)
    assert exits[7] == Exit(out_period=2, out_seconds_left=240.0)
    assert exits[8] == Exit()
    assert exits[9].ejected
