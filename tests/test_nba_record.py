import pandas as pd
import pytest

from edgefinder.tracking import nba_paper, nba_record

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
LINES = [{"player": "Cade Cunningham", "line": 24.5, "over_odds": -110, "under_odds": -110},
         {"player": "Duncan Robinson", "line": 13.5, "over_odds": -130, "under_odds": -102}]


def rows(version="ewma-v1", means=None, recorded="2026-11-04T17:00:00+00:00", stat="points",
         day="2026-11-04"):
    means = means or {"Cade Cunningham": 32.0, "Duncan Robinson": 8.0}
    predictions = {name: {"player_id": i, "mean": m}
                   for i, (name, m) in enumerate(means.items(), start=1)}
    return nba_paper.build_ledger_rows(EVENT, LINES, predictions, recorded, day,
                                       model_version=version, dispersion=7.8, stat=stat)


def ledger(*batches):
    return pd.DataFrame([r for batch in batches for r in batch], columns=nba_paper.COLUMNS)


def settle(ledger_, actuals, today="2026-11-06"):
    games = pd.DataFrame({
        "player_id": list(actuals), "game_date": pd.to_datetime(["2026-11-04"] * len(actuals)),
        "pts": list(actuals.values())})
    empty = pd.DataFrame(columns=["fetched_at", "phase", "event_id", "player", "line",
                                  "over_odds", "under_odds"])
    return nba_paper.settle(ledger_, games, empty, pd.Timestamp(today).date())


def test_only_picks_appear_in_the_record():
    picks = nba_record.locked_picks(ledger(rows()))
    assert set(picks["Player"]) <= {"Cade Cunningham", "Duncan Robinson"}
    assert len(picks) == 2 and picks["Bet"].str.contains("points").all()


def test_a_pick_says_what_the_bet_was_in_plain_words():
    picks = nba_record.locked_picks(ledger(rows())).set_index("Player")
    assert picks.loc["Cade Cunningham", "Bet"] == "Over 24.5 points"
    assert picks.loc["Duncan Robinson", "Bet"] == "Under 13.5 points"


def test_other_stats_are_worded_by_their_own_label():
    lines = [{"player": "Cade Cunningham", "line": 2.5, "over_odds": -110, "under_odds": -110}]
    batch = nba_paper.build_ledger_rows(
        EVENT, lines, {"Cade Cunningham": {"player_id": 1, "mean": 5.0}},
        "2026-11-04T17:00:00+00:00", "2026-11-04", stat="threes")
    assert nba_record.locked_picks(ledger(batch))["Bet"].iloc[0] == "Over 2.5 3-pointers"


def test_each_pick_shows_when_it_was_locked_and_how_long_before_tip_off():
    pick = nba_record.locked_picks(ledger(rows())).iloc[0]
    assert pick["Min before tip"] == 420                       # 17:00 UTC to 00:00 UTC
    assert str(pick["Locked"].tz) == "America/New_York"
    assert pick["Locked"].hour == 12                            # 17:00 UTC is noon in November


def test_the_newest_lock_comes_first():
    early = rows(recorded="2026-11-04T15:00:00+00:00")
    late = rows(version="minutes-v1", recorded="2026-11-04T19:00:00+00:00")
    locked = nba_record.locked_picks(ledger(early, late))
    assert locked["Model"].iloc[0] == "minutes-v1"


def test_integrity_counts_picks_recorded_at_or_after_tip_off():
    fine = rows(recorded="2026-11-04T17:00:00+00:00")
    # the builder refuses a late pick now, so make one the way an old or hand-edited file has it
    after = [{**row, "recorded_at": "2026-11-05T00:30:00+00:00"}
             for row in rows(version="late-model", recorded="2026-11-04T17:00:00+00:00")]
    report = nba_record.integrity(ledger(fine, after))
    assert report["picks"] == 4 and report["after_tip"] == 2
    assert nba_record.integrity(ledger(fine))["after_tip"] == 0


def test_a_pick_recorded_exactly_at_tip_off_counts_as_late():
    at_tip = [{**row, "recorded_at": "2026-11-05T00:00:00+00:00"} for row in rows()]
    assert nba_record.integrity(ledger(at_tip))["after_tip"] == 2


def test_integrity_reports_the_first_and_last_lock_and_how_many_are_graded():
    first = rows(recorded="2026-11-04T15:00:00+00:00")
    last = rows(version="minutes-v1", recorded="2026-11-04T19:00:00+00:00")
    settled = settle(ledger(first, last), {1: 30.0, 2: 10.0})
    report = nba_record.integrity(settled)
    assert report["first_lock"] < report["last_lock"]
    assert report["graded"] == report["picks"] == 4


def test_the_lead_time_reads_in_hours_and_minutes_and_flags_a_late_pick_loudly():
    assert nba_record.lead_label(425) == "7 h 5 min before tip"
    assert nba_record.lead_label(60) == "1 h 0 min before tip"
    assert nba_record.lead_label(45) == "45 min before tip"
    assert nba_record.lead_label(0) == "AFTER TIP-OFF"
    assert nba_record.lead_label(-12) == "AFTER TIP-OFF"


def test_an_empty_ledger_has_an_empty_record_and_clean_integrity():
    empty = pd.DataFrame(columns=nba_paper.COLUMNS)
    assert nba_record.locked_picks(empty).empty
    assert nba_record.integrity(empty) == {"picks": 0, "graded": 0, "after_tip": 0,
                                           "first_lock": None, "last_lock": None}
    assert nba_record.daily_results(nba_record.locked_picks(empty)).empty
    assert nba_record.cumulative_units(nba_record.locked_picks(empty)).empty


def test_results_fill_in_after_grading_and_nothing_else_changes():
    pending = ledger(rows())
    before = nba_record.locked_picks(pending).set_index("Player")
    after = nba_record.locked_picks(settle(pending, {1: 30.0, 2: 10.0})).set_index("Player")
    assert (before["Result"] == "").all()
    assert after.loc["Cade Cunningham", "Result"] == "win"        # over 24.5, scored 30
    assert after.loc["Duncan Robinson", "Result"] == "win"        # under 13.5, scored 10
    assert (before["Locked"] == after["Locked"]).all()            # the lock time never moves
    assert (before["Odds"] == after["Odds"]).all()


def test_daily_results_show_the_record_and_units_per_model():
    settled = settle(ledger(rows()), {1: 30.0, 2: 20.0})          # one win, one loss
    daily = nba_record.daily_results(nba_record.locked_picks(settled))
    assert len(daily) == 1
    row = daily.iloc[0]
    assert (row["Picks"], row["Graded"], row["Record"]) == (2, 2, "1-1")
    assert row["Units"] == pytest.approx(0.909090 - 1.0, abs=1e-3)   # +0.91 and -1


def test_a_day_with_nothing_graded_yet_shows_zero_graded_not_a_record():
    daily = nba_record.daily_results(nba_record.locked_picks(ledger(rows())))
    assert daily.iloc[0]["Graded"] == 0 and daily.iloc[0]["Record"] == "0-0"


def test_cumulative_units_run_up_and_down_by_game_day():
    day_one = rows(day="2026-11-04")
    day_two = rows(day="2026-11-05")
    for r in day_two:
        r["event_id"] = "e2"
    combined = ledger(day_one, day_two)
    games = pd.DataFrame({
        "player_id": [1, 2, 1, 2],
        "game_date": pd.to_datetime(["2026-11-04", "2026-11-04", "2026-11-05", "2026-11-05"]),
        "pts": [30.0, 10.0, 10.0, 30.0]})            # day one both win, day two both lose
    empty = pd.DataFrame(columns=["fetched_at", "phase", "event_id", "player", "line",
                                  "over_odds", "under_odds"])
    settled = nba_paper.settle(combined, games, empty, pd.Timestamp("2026-11-07").date())
    running = nba_record.cumulative_units(nba_record.locked_picks(settled))
    assert list(running["Game day"]) == ["2026-11-04", "2026-11-05"]
    assert running["Units"].iloc[0] > 0 > running["Units"].iloc[1] or \
        running["Units"].iloc[1] < running["Units"].iloc[0]


def test_calibration_groups_graded_lines_by_the_models_chance():
    settled = settle(ledger(rows()), {1: 30.0, 2: 10.0})
    bins = nba_record.calibration_bins(settled, "ewma-v1")
    assert bins["Lines"].sum() == 2
    assert set(bins.columns) == {"Model chance", "Lines", "Model said", "Market said",
                                 "Actually happened"}
    assert bins["Actually happened"].between(0, 100).all()


def test_calibration_with_nothing_graded_is_empty():
    assert nba_record.calibration_bins(ledger(rows()), "ewma-v1").empty


def test_the_verdict_refuses_to_judge_too_few_results():
    assert "No results yet" in nba_record.verdict(None, None, 0)
    assert "too few" in nba_record.verdict(0.24, 0.25, 40)
    assert "300" in nba_record.verdict(0.24, 0.25, 40)


def test_the_verdict_says_ahead_level_or_behind_once_there_is_enough_data():
    assert "Ahead of the market" in nba_record.verdict(0.240, 0.250, 500)
    assert "Behind the market" in nba_record.verdict(0.260, 0.250, 500)
    assert "Level with the market" in nba_record.verdict(0.2500, 0.2510, 500)


def test_even_a_good_verdict_does_not_overclaim():
    text = nba_record.verdict(0.240, 0.250, 500)
    assert "Still needs to hold up" in text


# ---- a pick can never be written once the game has started ------------------------------------------

def test_no_pick_is_recorded_at_or_after_tip_off():
    assert rows(recorded="2026-11-05T00:00:00+00:00") == []             # exactly at tip
    assert rows(recorded="2026-11-05T00:30:00+00:00") == []             # after
    assert len(rows(recorded="2026-11-04T23:59:59+00:00")) == 2         # one second before


def test_tipped_off_compares_real_moments_whatever_the_time_zone_spelling():
    assert nba_paper.tipped_off("2026-11-04T19:00:00-05:00", "2026-11-05T00:00:00Z")   # = 00:00Z
    assert not nba_paper.tipped_off("2026-11-04T18:59:59-05:00", "2026-11-05T00:00:00Z")


def test_x_plus_rows_follow_the_same_rule():
    from edgefinder.tracking import nba_alt
    lines = [{"player": "Cade Cunningham", "line": 24.5, "over_odds": 150}]
    predictions = {"Cade Cunningham": {"player_id": 1, "mean": 27.0}}
    late = nba_alt.build_alt_rows(EVENT, lines, predictions, "2026-11-05T00:00:00+00:00",
                                  "2026-11-04", model_version="ewma-v1", dispersion=7.8)
    early = nba_alt.build_alt_rows(EVENT, lines, predictions, "2026-11-04T20:00:00+00:00",
                                   "2026-11-04", model_version="ewma-v1", dispersion=7.8)
    assert late == [] and len(early) == 1


# ---- closing-line value summary -------------------------------------------------------------------------

def test_the_closing_value_summary_is_per_book_and_only_counts_picks_with_a_closing_price():
    frame = pd.DataFrame({
        "pick_side": ["over", "over", "under", None, "over"],
        "book": ["fanduel", "fanduel", "fanduel", "fanduel", "kalshi"],
        "clv_pct": [4.0, -2.0, None, 9.0, 1.5]})
    summary = nba_record.clv_summary(frame)
    # the non-pick (pick_side None) is ignored even though it has a number
    assert summary["fanduel"] == {"picks": 3, "measured": 2, "avg_clv_pct": 1.0,
                                  "beat_close_pct": 50.0}
    assert summary["kalshi"] == {"picks": 1, "measured": 1, "avg_clv_pct": 1.5,
                                 "beat_close_pct": 100.0}


def test_a_book_with_no_closing_prices_yet_shows_nothing_to_average():
    frame = pd.DataFrame({"pick_side": ["over"], "book": ["fanduel"], "clv_pct": [None]})
    assert nba_record.clv_summary(frame)["fanduel"] == {
        "picks": 1, "measured": 0, "avg_clv_pct": None, "beat_close_pct": None}
    assert nba_record.clv_summary(frame.iloc[0:0]) == {}
