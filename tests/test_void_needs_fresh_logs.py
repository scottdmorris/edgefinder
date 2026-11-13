"""A missing box score only means "did not play" when the game logs reach that day. If the
morning download failed and an older file was used, nothing may be voided: a void is permanent."""

import datetime as dt

import pandas as pd

from edgefinder.tracking import gap_log, nba_alt, nba_paper
from test_gap_log import box, logged
from test_nba_alt_extra import frame as alt_frame, row as alt_row
from test_nba_paper_extra import NO_SNAPSHOTS, frame, row

TODAY = dt.date(2026, 11, 6)          # the rows under test are for games on 2026-11-04


def logs(*days: str) -> pd.DataFrame:
    """Box scores for somebody else (player 99), one per day."""
    return pd.DataFrame({"player_id": [99] * len(days), "game_date": pd.to_datetime(list(days)),
                         "pts": [10.0] * len(days)})


def test_the_latest_logged_day_is_read_from_the_logs():
    assert nba_paper.latest_logged(logs("2026-11-02", "2026-11-04")) == "2026-11-04"
    assert nba_paper.latest_logged(logs()) == ""


def test_stale_logs_leave_a_past_row_pending_instead_of_voiding_it():
    out = nba_paper.settle(frame(row()), logs("2026-11-03"), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "status"] == "pending"


def test_empty_logs_void_nothing():
    out = nba_paper.settle(frame(row()), logs(), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "status"] == "pending"


def test_logs_that_reach_the_day_void_a_player_who_is_not_in_them():
    for latest in ("2026-11-04", "2026-11-05"):
        out = nba_paper.settle(frame(row()), logs(latest), NO_SNAPSHOTS, TODAY)
        assert out.loc[0, "status"] == "void" and out.loc[0, "pnl_units"] == 0.0


def test_the_x_plus_ledger_waits_for_fresh_logs_too():
    assert nba_alt.settle(alt_frame(alt_row()), logs("2026-11-03"), TODAY).loc[0, "status"] == "pending"
    assert nba_alt.settle(alt_frame(alt_row()), logs("2026-11-04"), TODAY).loc[0, "status"] == "void"


def test_price_gaps_wait_for_fresh_logs_too(tmp_path):
    log = logged(tmp_path)                                # a gap for a game on 2026-11-05
    stale = pd.DataFrame([box(99, 10.0, day="2026-11-04")])
    assert gap_log.settle(log, stale, TODAY).loc[0, "status"] == "pending"
    fresh = pd.DataFrame([box(99, 10.0, day="2026-11-05")])
    assert gap_log.settle(log, fresh, TODAY).loc[0, "status"] == "void"
