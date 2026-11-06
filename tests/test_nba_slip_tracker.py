import pandas as pd
import pytest

from edgefinder.data.nba_live import FINAL, LIVE, SCHEDULED, LiveGame, PlayerLine
from edgefinder.tracking import nba_slip_tracker as tracker
from edgefinder.tracking.nba_slip_tracker import ALIVE, HIT, MISSED, NOT_STARTED, VOID


def line(points=0, played=True, pid=1):
    return PlayerLine(player_id=pid, name="P", team="BOS", points=points, rebounds=0,
                      assists=0, minutes=10.0, played=played, on_court=False)


def game(status=LIVE, away="MIL", home="BOS", game_id="g1", away_score=40, home_score=50):
    return LiveGame(game_id=game_id, status=status, status_text="2nd Qtr", period=2,
                    clock="3:10", away=away, home=home, away_score=away_score,
                    home_score=home_score)


def test_a_half_point_line_needs_the_next_whole_number():
    assert tracker.target_points(24.5) == 25
    assert tracker.target_points(14.5) == 15
    assert tracker.target_points(9.5) == 10


def test_nothing_is_decided_before_tip_off():
    progress = tracker.leg_progress(True, 24.5, SCHEDULED, None)
    assert progress.status == NOT_STARTED and progress.have is None


def test_an_over_is_hit_the_moment_the_player_reaches_the_target_and_stays_hit():
    assert tracker.leg_progress(True, 24.5, LIVE, line(25)).status == HIT
    assert tracker.leg_progress(True, 24.5, LIVE, line(31)).status == HIT
    assert tracker.leg_progress(True, 24.5, FINAL, line(25)).status == HIT


def test_an_over_is_alive_while_the_game_is_on_and_missed_when_it_ends_short():
    live = tracker.leg_progress(True, 24.5, LIVE, line(20))
    assert live.status == ALIVE and "needs 5 more" in live.detail
    assert tracker.leg_progress(True, 24.5, FINAL, line(24)).status == MISSED


def test_an_under_is_missed_the_moment_the_player_reaches_the_target():
    assert tracker.leg_progress(False, 24.5, LIVE, line(25)).status == MISSED
    assert tracker.leg_progress(False, 24.5, FINAL, line(30)).status == MISSED


def test_an_under_is_alive_until_the_game_ends_then_hit():
    live = tracker.leg_progress(False, 24.5, LIVE, line(20))
    assert live.status == ALIVE and "4 more" in live.detail
    assert tracker.leg_progress(False, 24.5, FINAL, line(24)).status == HIT


def test_a_player_who_has_not_entered_a_live_game_is_still_alive():
    assert tracker.leg_progress(True, 24.5, LIVE, line(0, played=False)).status == ALIVE
    assert tracker.leg_progress(True, 24.5, LIVE, None).status == ALIVE


def test_a_player_who_never_played_voids_the_bet_once_the_game_is_final():
    assert tracker.leg_progress(True, 24.5, FINAL, line(0, played=False)).status == VOID
    assert tracker.leg_progress(False, 24.5, FINAL, None).status == VOID


def test_one_missed_bet_sinks_the_slip_immediately():
    assert tracker.slip_status([HIT, ALIVE, MISSED]) == MISSED


def test_a_slip_is_hit_only_when_every_counting_bet_is_hit():
    assert tracker.slip_status([HIT, HIT]) == HIT
    assert tracker.slip_status([HIT, ALIVE]) == ALIVE
    assert tracker.slip_status([HIT, NOT_STARTED]) == ALIVE


def test_a_voided_bet_drops_out_of_the_slip_instead_of_sinking_it():
    assert tracker.slip_status([HIT, VOID]) == HIT
    assert tracker.slip_status([VOID, VOID]) == VOID
    assert tracker.slip_status([ALIVE, VOID]) == ALIVE


def test_a_slip_nobody_has_started_is_not_started():
    assert tracker.slip_status([NOT_STARTED, NOT_STARTED]) == NOT_STARTED


def bets(*rows):
    return pd.DataFrame(rows)


def bet(label, pid, over, line_, away="MIL", home="BOS"):
    return {"Leg": label, "player_id": pid, "is_over": over, "line": line_,
            "away_abbr": away, "home_abbr": home}


def test_each_bet_is_matched_to_its_game_and_its_player():
    chosen = bets(bet("A over", 1, True, 24.5), bet("B under", 2, False, 10.5))
    boxes = {"g1": {1: line(26, pid=1), 2: line(12, pid=2)}}
    result = tracker.track_slip(chosen, [game()], lambda gid: boxes[gid])
    assert list(result["Status"]) == [HIT, MISSED]
    assert list(result["Have"]) == [26, 12]
    assert result["Progress"].tolist() == [1.0, 1.0]


def test_a_game_is_only_fetched_once_however_many_bets_are_in_it():
    calls = []

    def fetch(game_id):
        calls.append(game_id)
        return {1: line(5, pid=1), 2: line(5, pid=2)}

    chosen = bets(bet("A", 1, True, 24.5), bet("B", 2, True, 24.5))
    tracker.track_slip(chosen, [game()], fetch)
    assert calls == ["g1"]


def test_a_game_that_has_not_started_is_not_fetched_at_all():
    def fetch(game_id):
        raise AssertionError("should not be called")

    result = tracker.track_slip(bets(bet("A", 1, True, 24.5)), [game(SCHEDULED)], fetch)
    assert result["Status"].iloc[0] == NOT_STARTED


def test_a_bet_with_no_matching_game_says_so_instead_of_failing():
    chosen = bets(bet("A", 1, True, 24.5, away="XXX", home="YYY"))
    result = tracker.track_slip(chosen, [game()], lambda gid: {})
    assert result["Status"].iloc[0] == NOT_STARTED
    assert "no live game" in result["Detail"].iloc[0]


def test_progress_is_the_share_of_the_target_reached():
    chosen = bets(bet("A", 1, True, 24.5))
    result = tracker.track_slip(chosen, [game()], lambda gid: {1: line(10, pid=1)})
    assert result["Progress"].iloc[0] == pytest.approx(10 / 25)


def test_the_game_text_shows_the_score_and_clock_for_a_live_game():
    assert tracker.game_text(game()) == "MIL 40 - BOS 50  ·  2nd Qtr 3:10"
    assert "BOS" in tracker.game_text(game(SCHEDULED)) and "@" in tracker.game_text(game(SCHEDULED))
    assert tracker.game_text(None) == "no live game"


def test_a_rebounds_bet_counts_rebounds_not_points():
    player = PlayerLine(player_id=1, name="P", team="BOS", points=30, rebounds=6, assists=2,
                        minutes=30.0, played=True, on_court=True, threes=1)
    progress = tracker.leg_progress(True, 9.5, LIVE, player, stat="rebounds")
    assert progress.status == ALIVE and progress.have == 6
    assert "rebounds" in progress.detail


@pytest.mark.parametrize("stat, have", [("points", 30), ("rebounds", 6), ("assists", 2),
                                        ("threes", 1)])
def test_each_stat_is_read_from_its_own_box_score_column(stat, have):
    player = PlayerLine(player_id=1, name="P", team="BOS", points=30, rebounds=6, assists=2,
                        minutes=30.0, played=True, on_court=True, threes=1)
    assert tracker.leg_progress(True, 0.5, LIVE, player, stat=stat).have == have


def test_a_slip_tracks_each_bet_by_its_own_stat():
    chosen = bets({**bet("A reb", 1, True, 7.5), "stat_key": "rebounds"},
                  {**bet("B pts", 2, True, 7.5), "stat_key": "points"})
    box = {1: PlayerLine(player_id=1, name="A", team="BOS", points=20, rebounds=3, assists=0,
                         minutes=20.0, played=True, on_court=True),
           2: line(20, pid=2)}
    result = tracker.track_slip(chosen, [game()], lambda gid: box)
    assert list(result["Status"]) == [ALIVE, HIT]
    assert list(result["Have"]) == [3, 20]
