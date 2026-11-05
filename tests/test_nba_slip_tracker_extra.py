"""Truth tables for hit / alive / missed decisions on live box scores."""

import itertools

import pandas as pd
import pytest

from edgefinder.data.nba_live import FINAL, LIVE, SCHEDULED, LiveGame, PlayerLine
from edgefinder.tracking import nba_slip_tracker as tracker
from edgefinder.tracking.nba_slip_tracker import ALIVE, HIT, MISSED, NOT_STARTED, VOID


def player(points, played=True, pid=1):
    return PlayerLine(player_id=pid, name="P", team="BOS", points=points, rebounds=0,
                      assists=0, minutes=12.0, played=played, on_court=True)


def live_game(status=LIVE, away="MIL", home="BOS", game_id="g1", clock="3:10", text="2nd Qtr"):
    return LiveGame(game_id=game_id, status=status, status_text=text, period=2, clock=clock,
                    away=away, home=home, away_score=51, home_score=48)


# ---- target points --------------------------------------------------------------------------------

@pytest.mark.parametrize("line, target", [(24.5, 25), (0.5, 1), (9.5, 10), (29.5, 30)])
def test_target_is_the_fewest_points_that_beat_the_line(line, target):
    assert tracker.target_points(line) == target


# ---- the full truth table for one bet ------------------------------------------------------------------
# line 24.5 -> target 25. Columns: over?, game status, points, expected status.

@pytest.mark.parametrize("is_over, status, points, expected", [
    # over / X+
    (True, LIVE, 24, ALIVE), (True, LIVE, 25, HIT), (True, LIVE, 40, HIT),
    (True, FINAL, 24, MISSED), (True, FINAL, 25, HIT), (True, FINAL, 0, MISSED),
    # under
    (False, LIVE, 24, ALIVE), (False, LIVE, 25, MISSED), (False, LIVE, 40, MISSED),
    (False, FINAL, 24, HIT), (False, FINAL, 25, MISSED), (False, FINAL, 0, HIT),
])
def test_bet_status_for_a_player_who_played(is_over, status, points, expected):
    assert tracker.leg_progress(is_over, 24.5, status, player(points)).status == expected


@pytest.mark.parametrize("is_over", [True, False])
def test_nothing_is_decided_before_tip_off_for_either_side(is_over):
    progress = tracker.leg_progress(is_over, 24.5, SCHEDULED, player(30))
    assert progress.status == NOT_STARTED and progress.have is None and progress.target == 25


@pytest.mark.parametrize("is_over", [True, False])
def test_a_player_who_never_entered_is_void_once_final_and_alive_while_live(is_over):
    assert tracker.leg_progress(is_over, 24.5, FINAL, None).status == VOID
    assert tracker.leg_progress(is_over, 24.5, FINAL, player(0, played=False)).status == VOID
    alive = tracker.leg_progress(is_over, 24.5, LIVE, player(0, played=False))
    assert alive.status == ALIVE and alive.have == 0


def test_an_over_that_hit_stays_hit_even_if_the_game_is_still_live():
    # points never go down, so reaching the target is permanent
    assert tracker.leg_progress(True, 24.5, LIVE, player(26)).status == HIT


def test_an_under_that_missed_stays_missed_even_if_the_game_is_still_live():
    assert tracker.leg_progress(False, 24.5, LIVE, player(26)).status == MISSED


def test_over_and_under_on_the_same_line_are_never_both_hit_or_both_missed():
    for status, points in itertools.product((LIVE, FINAL), range(0, 40)):
        over = tracker.leg_progress(True, 24.5, status, player(points)).status
        under = tracker.leg_progress(False, 24.5, status, player(points)).status
        assert {over, under} != {HIT}, (status, points)
        assert {over, under} != {MISSED}, (status, points)


def test_progress_text_counts_the_points_still_needed():
    over = tracker.leg_progress(True, 24.5, LIVE, player(20))
    assert over.have == 20 and over.target == 25 and "needs 5 more" in over.detail
    under = tracker.leg_progress(False, 24.5, LIVE, player(20))
    assert "can score 4 more" in under.detail           # 24 is the most that still wins


# ---- the whole slip ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("statuses, expected", [
    ([HIT, HIT], HIT),
    ([HIT, ALIVE], ALIVE),
    ([HIT, MISSED], MISSED),
    ([ALIVE, MISSED, HIT], MISSED),            # one miss kills the slip, whatever else is happening
    ([NOT_STARTED, NOT_STARTED], NOT_STARTED),
    ([NOT_STARTED, HIT], ALIVE),
    ([NOT_STARTED, ALIVE], ALIVE),
    ([HIT, VOID], HIT),                        # a void leg drops out; the rest decide
    ([HIT, VOID, ALIVE], ALIVE),
    ([VOID, MISSED], MISSED),
    ([VOID, VOID], VOID),
    ([VOID, NOT_STARTED], NOT_STARTED),
    ([], VOID),
])
def test_slip_status_truth_table(statuses, expected):
    assert tracker.slip_status(statuses) == expected


def test_slip_status_ignores_the_order_of_the_legs():
    statuses = [HIT, ALIVE, VOID, NOT_STARTED]
    for ordering in itertools.permutations(statuses):
        assert tracker.slip_status(list(ordering)) == ALIVE


# ---- tracking a slip -----------------------------------------------------------------------------------------------------

def chosen(*bets):
    columns = ["Leg", "player_id", "is_over", "line", "away_abbr", "home_abbr"]
    return pd.DataFrame(list(bets), columns=columns)


def bet(pid, is_over=True, line=24.5, away="MIL", home="BOS"):
    return (f"P{pid}", pid, is_over, line, away, home)


def test_the_box_score_is_fetched_once_per_started_game():
    calls = []

    def fetch(game_id):
        calls.append(game_id)
        return {1: player(30, pid=1), 2: player(10, pid=2)}

    table = tracker.track_slip(chosen(bet(1), bet(2, is_over=False)), [live_game()], fetch)
    assert calls == ["g1"]
    assert list(table["Status"]) == [HIT, ALIVE]


def test_a_game_that_has_not_started_is_never_fetched():
    def fetch(game_id):
        raise AssertionError("box score requested for a scheduled game")

    table = tracker.track_slip(chosen(bet(1)), [live_game(status=SCHEDULED)], fetch)
    assert table.loc[0, "Status"] == NOT_STARTED and table.loc[0, "Progress"] == 0.0


def test_a_bet_with_no_matching_game_is_not_started_with_a_reason():
    table = tracker.track_slip(chosen(bet(1, away="LAL", home="DEN")), [live_game()],
                               lambda game_id: {})
    assert table.loc[0, "Status"] == NOT_STARTED
    assert "no live game" in table.loc[0, "Detail"] and table.loc[0, "Game"] == "no live game"


def test_a_player_missing_from_the_box_score_is_alive_while_live_and_void_when_final():
    live = tracker.track_slip(chosen(bet(9)), [live_game()], lambda game_id: {})
    assert live.loc[0, "Status"] == ALIVE
    final = tracker.track_slip(chosen(bet(9)), [live_game(status=FINAL)], lambda game_id: {})
    assert final.loc[0, "Status"] == VOID


def test_progress_bar_fraction_is_have_over_target_capped_at_one():
    box = {1: player(10, pid=1), 2: player(40, pid=2)}
    table = tracker.track_slip(chosen(bet(1), bet(2)), [live_game()], lambda game_id: box)
    assert table.loc[0, "Progress"] == pytest.approx(10 / 25)
    assert table.loc[1, "Progress"] == 1.0


def test_two_games_are_each_fetched_once():
    calls = []

    def fetch(game_id):
        calls.append(game_id)
        return {1: player(5, pid=1), 2: player(5, pid=2), 3: player(5, pid=3)}

    games = [live_game(game_id="g1"), live_game(game_id="g2", away="LAL", home="DEN")]
    tracker.track_slip(chosen(bet(1), bet(2), bet(3, away="LAL", home="DEN")), games, fetch)
    assert sorted(calls) == ["g1", "g2"]


def test_find_game_matches_on_both_teams():
    games = [live_game(), live_game(away="BOS", home="MIL", game_id="g2")]
    assert tracker.find_game(games, "BOS", "MIL").game_id == "g2"
    assert tracker.find_game(games, "MIL", "BOS").game_id == "g1"
    assert tracker.find_game(games, "MIL", "MIL") is None
    assert tracker.find_game(games, None, None) is None


# ---- game text ----------------------------------------------------------------------------------------------------------

def test_game_text_for_each_phase():
    assert tracker.game_text(None) == "no live game"
    assert tracker.game_text(live_game()) == "MIL 51 - BOS 48  ·  2nd Qtr 3:10"
    assert tracker.game_text(live_game(clock="")) == "MIL 51 - BOS 48  ·  2nd Qtr"
    assert tracker.game_text(live_game(status=FINAL, text="Final")) \
        == "MIL 51 - BOS 48  ·  Final"
    assert tracker.game_text(live_game(status=SCHEDULED, text="7:30 pm ET")) \
        == "MIL @ BOS  ·  7:30 pm ET"
