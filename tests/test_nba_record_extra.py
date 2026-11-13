"""Hand-verified checks on the public record: lock times, integrity counts,
running profit and calibration bins."""

import pandas as pd
import pytest

from edgefinder.tracking import nba_paper, nba_record

TIP = "2026-11-05T00:00:00Z"            # 7:00 pm Eastern on Nov 4 (EST, UTC-5)


def row(**overrides):
    base = {c: None for c in nba_paper.COLUMNS} | {
        "game_date": "2026-11-04", "event_id": "e1", "commence_time": TIP,
        "recorded_at": "2026-11-04T20:00:00+00:00", "player": "A", "player_id": 1,
        "line": 24.5, "over_odds": -110, "under_odds": -110, "model_version": "ewma-v1",
        "model_p_over": 0.6, "fair_p_over": 0.5, "pick_side": "over", "pick_odds": -110,
        "status": "pending", "stat": "points", "book": "fanduel"}
    return base | overrides


def frame(*rows):
    return pd.DataFrame(list(rows), columns=nba_paper.COLUMNS)


# ---- locked picks -------------------------------------------------------------------------------

def test_lead_time_and_eastern_lock_time_by_hand():
    # 20:00 UTC is 15:00 EST ; tip 00:00 UTC is 4 hours later = 240 minutes
    locked = nba_record.locked_picks(frame(row()))
    assert locked.loc[0, "Min before tip"] == 240.0
    assert locked.loc[0, "Locked"].hour == 15
    assert locked.loc[0, "Bet"] == "Over 24.5 points"


def test_rows_without_a_pick_are_not_in_the_record():
    locked = nba_record.locked_picks(frame(row(), row(player="B", pick_side=None)))
    assert list(locked["Player"]) == ["A"]


def test_no_picks_gives_an_empty_table_with_the_columns():
    locked = nba_record.locked_picks(frame(row(pick_side=None)))
    assert locked.empty and "Min before tip" in locked.columns


def test_newest_lock_comes_first():
    locked = nba_record.locked_picks(frame(
        row(player="early", recorded_at="2026-11-04T17:00:00+00:00"),
        row(player="late", recorded_at="2026-11-04T21:00:00+00:00")))
    assert list(locked["Player"]) == ["late", "early"]


def test_the_bet_names_the_stat_and_defaults_legacy_rows_to_points():
    locked = nba_record.locked_picks(frame(
        row(player="R", stat="rebounds", line=9.5, pick_side="under"),
        row(player="L", stat=None)))
    bets = dict(zip(locked["Player"], locked["Bet"]))
    assert bets["R"] == "Under 9.5 rebounds" and bets["L"] == "Over 24.5 points"
    assert dict(zip(locked["Player"], locked["stat"]))["L"] == "points"


def test_an_unknown_result_shows_as_empty_text():
    locked = nba_record.locked_picks(frame(row()))
    assert locked.loc[0, "Result"] == ""


# ---- integrity --------------------------------------------------------------------------------------

def test_a_clean_record_has_no_pick_after_tip():
    facts = nba_record.integrity(frame(
        row(), row(player="B", recorded_at="2026-11-04T23:00:00+00:00", status="settled"),
        row(player="C", status="void")))
    assert facts["picks"] == 3 and facts["graded"] == 2 and facts["after_tip"] == 0


def test_picks_recorded_at_or_after_tip_off_are_counted():
    facts = nba_record.integrity(frame(
        row(player="at", recorded_at="2026-11-05T00:00:00+00:00"),       # exactly at tip
        row(player="after", recorded_at="2026-11-05T00:30:00+00:00"),    # 30 min late
        row(player="ok", recorded_at="2026-11-04T23:00:00+00:00")))      # 60 min early
    assert facts["after_tip"] == 2


def test_first_and_last_lock():
    facts = nba_record.integrity(frame(
        row(player="a", recorded_at="2026-11-04T17:00:00+00:00"),
        row(player="b", recorded_at="2026-11-04T21:00:00+00:00")))
    assert facts["first_lock"].hour == 12 and facts["last_lock"].hour == 16


def test_integrity_of_an_empty_record():
    assert nba_record.integrity(frame()) == {
        "picks": 0, "graded": 0, "after_tip": 0, "first_lock": None, "last_lock": None}


def test_a_pick_locked_twenty_seconds_before_tip_is_not_after_tip():
    facts = nba_record.integrity(frame(row(recorded_at="2026-11-04T23:59:40+00:00")))
    assert facts["after_tip"] == 0


# ---- lead label ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("minutes, text", [
    (425, "7 h 5 min before tip"),
    (60, "1 h 0 min before tip"),
    (59, "59 min before tip"),
    (1, "1 min before tip"),
    (0, "AFTER TIP-OFF"),
    (-12, "AFTER TIP-OFF"),
])
def test_lead_label(minutes, text):
    assert nba_record.lead_label(minutes) == text


# ---- grading and running profit -------------------------------------------------------------------------------

def graded_set():
    return nba_record.locked_picks(frame(
        row(player="a", game_date="2026-11-01", status="settled", result="win", pnl_units=1.0),
        row(player="b", game_date="2026-11-02", status="settled", result="loss", pnl_units=-1.0),
        row(player="c", game_date="2026-11-03", status="settled", result="win", pnl_units=0.9),
        row(player="d", game_date="2026-11-03", status="void", pnl_units=0.0),
        row(player="e", game_date="2026-11-04", status="pending")))


def test_graded_keeps_only_wins_and_losses_in_game_order():
    done = nba_record.graded(graded_set())
    assert list(done["Player"]) == ["a", "b", "c"]


def test_cumulative_units_run_by_hand():
    # +1.0 ; +1.0 - 1.0 = 0.0 ; 0.0 + 0.9 = 0.9
    running = nba_record.cumulative_units(graded_set())
    assert list(running["Units"]) == pytest.approx([1.0, 0.0, 0.9])
    assert list(running["Game day"]) == ["2026-11-01", "2026-11-02", "2026-11-03"]


def test_cumulative_units_are_kept_separately_per_model():
    locked = nba_record.locked_picks(frame(
        row(player="a", game_date="2026-11-01", status="settled", result="win", pnl_units=1.0),
        row(player="b", game_date="2026-11-01", model_version="minutes-v1", status="settled",
            result="loss", pnl_units=-1.0),
        row(player="c", game_date="2026-11-02", model_version="minutes-v1", status="settled",
            result="loss", pnl_units=-1.0)))
    running = nba_record.cumulative_units(locked)
    by_model = {m: list(g["Units"]) for m, g in running.groupby("Model")}
    assert by_model == {"ewma-v1": [1.0], "minutes-v1": [-1.0, -2.0]}


def test_cumulative_units_with_nothing_graded_is_empty():
    assert nba_record.cumulative_units(nba_record.locked_picks(frame(row()))).empty


def test_daily_results_by_hand():
    daily = nba_record.daily_results(graded_set())
    nov3 = daily[daily["Game day"] == "2026-11-03"].iloc[0]
    assert nov3["Picks"] == 2 and nov3["Graded"] == 1       # the void pick is not graded
    assert nov3["Record"] == "1-0" and nov3["Units"] == pytest.approx(0.9)
    nov2 = daily[daily["Game day"] == "2026-11-02"].iloc[0]
    assert nov2["Record"] == "0-1" and nov2["Units"] == pytest.approx(-1.0)
    assert list(daily["Game day"]) == sorted(daily["Game day"], reverse=True)


def test_daily_results_total_units_equal_the_sum_of_the_picks():
    daily = nba_record.daily_results(graded_set())
    assert daily["Units"].sum() == pytest.approx(1.0 - 1.0 + 0.9)


def test_daily_results_of_an_empty_record():
    empty = nba_record.daily_results(nba_record.locked_picks(frame()))
    assert empty.empty and list(empty.columns) == [
        "Game day", "Model", "Picks", "Graded", "Record", "Units"]


# ---- calibration bins ------------------------------------------------------------------------------------------------

def settled(p, happened, fair=0.5, **extra):
    return row(model_p_over=p, fair_p_over=fair, went_over=happened, status="settled",
               player=f"p{p}-{happened}-{len(extra)}", **extra)


def test_calibration_bins_by_hand():
    # bin 0-20%: p .10 and .15 -> avg 12.5, both stayed under -> 0
    # bin 60-80%: p .70 and .75 -> avg 72.5, one went over -> 50
    # bin 80-100%: p 1.0 (lowest/highest edges included) -> 100, went over -> 100
    bins = nba_record.calibration_bins(frame(
        settled(0.10, False, fair=0.4), settled(0.15, False, fair=0.5),
        settled(0.70, True, fair=0.6), settled(0.75, False, fair=0.5),
        settled(1.0, True, fair=0.9)), "ewma-v1").set_index("Model chance")
    first = bins.iloc[0]                    # the 0-20% bin
    assert first["Lines"] == 2
    assert first["Model said"] == pytest.approx(12.5)
    assert first["Market said"] == pytest.approx(45.0)
    assert first["Actually happened"] == pytest.approx(0.0)
    assert bins.loc["60-80%", "Model said"] == pytest.approx(72.5)
    assert bins.loc["60-80%", "Actually happened"] == pytest.approx(50.0)
    assert bins.loc["80-100%", "Lines"] == 1
    assert bins.loc["80-100%", "Actually happened"] == pytest.approx(100.0)
    assert bins["Lines"].sum() == 5


def test_a_probability_of_exactly_zero_lands_in_the_first_bin():
    bins = nba_record.calibration_bins(frame(settled(0.0, False)), "ewma-v1")
    assert bins.loc[0, "Lines"] == 1 and bins.loc[0, "Model said"] == 0.0


def test_the_first_bin_is_labelled_zero_to_twenty_percent():
    bins = nba_record.calibration_bins(frame(settled(0.1, False)), "ewma-v1")
    assert bins.loc[0, "Model chance"] == "0-20%"


def test_only_the_asked_model_and_only_settled_lines_count():
    bins = nba_record.calibration_bins(frame(
        settled(0.5, True),
        row(player="x", model_version="minutes-v1", model_p_over=0.5, went_over=True,
            status="settled"),
        row(player="y", model_p_over=0.5, went_over=None, status="pending")), "ewma-v1")
    assert bins["Lines"].sum() == 1


def test_calibration_bins_with_no_results_is_empty():
    bins = nba_record.calibration_bins(frame(row()), "ewma-v1")
    assert bins.empty and list(bins.columns) == [
        "Model chance", "Lines", "Model said", "Market said", "Actually happened"]


# ---- verdict ---------------------------------------------------------------------------------------------------------------

def test_no_results_yet():
    assert "No results yet" in nba_record.verdict(None, None, 0)
    assert "No results yet" in nba_record.verdict(0.2, 0.25, 0)
    assert "No results yet" in nba_record.verdict(None, 0.25, 50)


def test_too_few_lines_refuses_to_judge():
    text = nba_record.verdict(0.20, 0.25, 299)
    assert "299 lines" in text and "too few" in text and "300" in text


def test_exactly_the_minimum_is_enough_to_judge():
    assert "too few" not in nba_record.verdict(0.20, 0.25, 300)


def test_ahead_of_the_market_quotes_the_gap():
    # 0.2500 - 0.2300 = 0.0200
    text = nba_record.verdict(0.23, 0.25, 500)
    assert text.startswith("Ahead of the market") and "0.0200" in text


def test_behind_the_market_quotes_the_gap():
    text = nba_record.verdict(0.27, 0.25, 500)
    assert text.startswith("Behind the market") and "0.0200" in text


def test_a_gap_under_two_thousandths_is_called_level():
    assert nba_record.verdict(0.2490, 0.2500, 500).startswith("Level with the market")
    assert nba_record.verdict(0.2510, 0.2500, 500).startswith("Level with the market")
    assert not nba_record.verdict(0.2470, 0.2500, 500).startswith("Level")


def test_a_custom_minimum_is_respected():
    assert "too few" in nba_record.verdict(0.20, 0.25, 40, minimum=50)
    assert "too few" not in nba_record.verdict(0.20, 0.25, 50, minimum=50)
