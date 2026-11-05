import datetime as dt

import pandas as pd
import pytest

from edgefinder.betting.odds_math import american_to_decimal, implied_prob
from edgefinder.tracking import nba_paper

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
RECORDED_AT = "2026-11-04T17:00:00+00:00"
GAME_DATE = "2026-11-04"


def build(lines, predictions):
    return nba_paper.build_ledger_rows(EVENT, lines, predictions, RECORDED_AT, GAME_DATE)


def line(player="Cade Cunningham", point=24.5, over=-110, under=-110):
    return {"player": player, "line": point, "over_odds": over, "under_odds": under}


def prediction(mean=24.5, player_id=1):
    return {"player_id": player_id, "mean": mean}


def test_a_much_higher_projection_creates_an_over_pick():
    rows = build([line()], {"Cade Cunningham": prediction(mean=32.0)})
    assert len(rows) == 1
    row = rows[0]
    assert row["pick_side"] == "over"
    assert row["pick_ev"] >= nba_paper.MIN_EV_TO_RECORD
    assert row["pick_odds"] == -110
    assert row["status"] == "pending"
    assert row["model_version"] == nba_paper.MODEL_VERSION


def test_a_much_lower_projection_creates_an_under_pick():
    row = build([line()], {"Cade Cunningham": prediction(mean=16.0)})[0]
    assert row["pick_side"] == "under"


def test_a_projection_at_the_line_is_logged_but_not_picked():
    row = build([line()], {"Cade Cunningham": prediction(mean=24.5)})[0]
    assert row["pick_side"] is None
    assert row["pick_ev"] is None
    assert 0.3 < row["model_p_over"] < 0.7  # still scored for calibration


def test_the_market_probability_is_devigged():
    row = build([line(over=-130, under=-102)], {"Cade Cunningham": prediction()})[0]
    over, under = implied_prob(-130), implied_prob(-102)
    assert row["fair_p_over"] == pytest.approx(over / (over + under))


def test_lines_without_both_prices_are_skipped():
    rows = build([line(under=None), line(player="Other", over=None)],
                 {"Cade Cunningham": prediction(), "Other": prediction(player_id=2)})
    assert rows == []


def test_whole_number_lines_are_skipped_because_they_can_push():
    assert build([line(point=24.0)], {"Cade Cunningham": prediction()}) == []


def test_players_without_a_projection_are_skipped():
    assert build([line(player="Unmatched Rookie")], {"Cade Cunningham": prediction()}) == []


def test_pick_ev_uses_the_blend_of_model_and_market():
    row = build([line()], {"Cade Cunningham": prediction(mean=32.0)})[0]
    blend = (nba_paper.MODEL_WEIGHT * row["model_p_over"]
             + (1 - nba_paper.MODEL_WEIGHT) * row["fair_p_over"])
    decimal = american_to_decimal(-110)
    assert row["pick_ev"] == pytest.approx(blend * (decimal - 1) - (1 - blend))


def test_recording_twice_does_not_duplicate_rows(tmp_path):
    path = tmp_path / "log.csv"
    rows = build([line()], {"Cade Cunningham": prediction(mean=32.0)})
    assert nba_paper.append_rows(rows, path=path) == 1
    assert nba_paper.append_rows(rows, path=path) == 0
    assert len(nba_paper.load_ledger(path=path)) == 1


def ledger_with(rows):
    return pd.DataFrame(rows, columns=nba_paper.COLUMNS)


def games_frame(entries):
    """entries: (player_id, 'YYYY-MM-DD', pts)"""
    return pd.DataFrame(entries, columns=["player_id", "game_date", "pts"]).assign(
        game_date=lambda f: pd.to_datetime(f["game_date"]))


def empty_snapshots():
    return pd.DataFrame(columns=["fetched_at", "phase", "event_id", "player",
                                 "line", "over_odds", "under_odds"])


TODAY_AFTER = dt.date(2026, 11, 6)
TODAY_SAME = dt.date(2026, 11, 4)


def pending_over_pick(mean=32.0):
    return build([line()], {"Cade Cunningham": prediction(mean=mean)})


def test_an_over_pick_wins_when_the_player_scores_more_than_the_line():
    settled = nba_paper.settle(
        ledger_with(pending_over_pick()), games_frame([(1, GAME_DATE, 30)]),
        empty_snapshots(), TODAY_AFTER)
    row = settled.iloc[0]
    assert row["status"] == "settled"
    assert row["actual"] == 30
    assert bool(row["went_over"]) is True
    assert row["result"] == "win"
    assert row["pnl_units"] == pytest.approx(american_to_decimal(-110) - 1)


def test_an_over_pick_loses_when_the_player_scores_less():
    settled = nba_paper.settle(
        ledger_with(pending_over_pick()), games_frame([(1, GAME_DATE, 20)]),
        empty_snapshots(), TODAY_AFTER)
    row = settled.iloc[0]
    assert row["result"] == "loss"
    assert row["pnl_units"] == -1.0


def test_a_player_who_did_not_play_voids_the_row_once_the_day_has_passed():
    settled = nba_paper.settle(
        ledger_with(pending_over_pick()), games_frame([(99, GAME_DATE, 10)]),
        empty_snapshots(), TODAY_AFTER)
    row = settled.iloc[0]
    assert row["status"] == "void"
    assert row["pnl_units"] == 0.0


def test_rows_stay_pending_while_the_game_day_is_not_over():
    settled = nba_paper.settle(
        ledger_with(pending_over_pick()), games_frame([(99, GAME_DATE, 10)]),
        empty_snapshots(), TODAY_SAME)
    assert settled.iloc[0]["status"] == "pending"


def late_snapshot(point=24.5, over=-125, under=105):
    return pd.DataFrame([{
        "fetched_at": "2026-11-04T23:45:00+00:00", "phase": "late", "event_id": "e1",
        "player": "Cade Cunningham", "line": point, "over_odds": over, "under_odds": under,
    }])


def test_clv_compares_the_pick_price_with_the_closing_price_at_the_same_line():
    settled = nba_paper.settle(
        ledger_with(pending_over_pick()), games_frame([(1, GAME_DATE, 30)]),
        late_snapshot(over=-125), TODAY_AFTER)
    row = settled.iloc[0]
    placed, closed = implied_prob(-110), implied_prob(-125)
    assert row["closing_over_odds"] == -125
    assert row["clv_pct"] == pytest.approx((closed - placed) / placed * 100)
    assert row["line_move"] == 0.0


def test_when_the_line_moved_clv_is_reported_as_points_of_line_movement():
    settled = nba_paper.settle(
        ledger_with(pending_over_pick()), games_frame([(1, GAME_DATE, 30)]),
        late_snapshot(point=25.5), TODAY_AFTER)
    row = settled.iloc[0]
    assert pd.isna(row["clv_pct"])
    assert row["line_move"] == pytest.approx(1.0)  # over at 24.5 beat the 25.5 close


def test_under_picks_gain_when_the_line_falls():
    under_pick = build([line()], {"Cade Cunningham": prediction(mean=16.0)})
    settled = nba_paper.settle(
        ledger_with(under_pick), games_frame([(1, GAME_DATE, 10)]),
        late_snapshot(point=23.5), TODAY_AFTER)
    assert settled.iloc[0]["line_move"] == pytest.approx(1.0)


def test_summary_reports_record_units_and_clv():
    rows = pending_over_pick() + build(
        [line(player="Second Guy", point=20.5)],
        {"Second Guy": prediction(mean=28.0, player_id=2)})
    games = games_frame([(1, GAME_DATE, 30), (2, GAME_DATE, 15)])
    settled = nba_paper.settle(ledger_with(rows), games, late_snapshot(over=-125), TODAY_AFTER)
    summary = nba_paper.summary(settled)
    assert summary["picks"] == 2
    assert summary["settled"] == 2
    assert summary["record"] == "1-1"
    assert summary["units"] == pytest.approx(american_to_decimal(-110) - 2)


def test_calibration_compares_the_model_with_the_market_on_every_line():
    frame = pd.DataFrame({
        "status": ["settled"] * 4 + ["void", "pending"],
        "went_over": [1, 0, 1, 0, None, None],
        "model_p_over": [1.0, 0.0, 1.0, 0.0, 0.9, 0.9],   # perfect
        "fair_p_over": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5],    # coin flip
    })
    result = nba_paper.calibration_summary(frame)
    assert result["n"] == 4
    assert result["brier_model"] == pytest.approx(0.0)
    assert result["brier_market"] == pytest.approx(0.25)


def two_version_rows():
    champion = build([line()], {"Cade Cunningham": prediction(mean=32.0)})
    challenger = nba_paper.build_ledger_rows(
        EVENT, [line()], {"Cade Cunningham": prediction(mean=16.0)},
        RECORDED_AT, GAME_DATE, model_version="challenger")
    return champion + challenger


def test_the_model_version_and_dispersion_can_be_overridden():
    wide = nba_paper.build_ledger_rows(
        EVENT, [line()], {"Cade Cunningham": prediction(mean=32.0)}, RECORDED_AT, GAME_DATE,
        model_version="challenger", dispersion=2.0)[0]
    default = build([line()], {"Cade Cunningham": prediction(mean=32.0)})[0]
    assert wide["model_version"] == "challenger"
    assert wide["model_p_over"] < default["model_p_over"]   # more spread, less sure of the over


def test_two_model_versions_can_record_the_same_line(tmp_path):
    path = tmp_path / "log.csv"
    rows = two_version_rows()
    assert nba_paper.append_rows(rows[:1], path=path) == 1
    assert nba_paper.append_rows(rows[1:], path=path) == 1
    assert len(nba_paper.load_ledger(path=path)) == 2


def test_summary_can_be_limited_to_one_model_version():
    settled = nba_paper.settle(
        ledger_with(two_version_rows()), games_frame([(1, GAME_DATE, 30)]),
        empty_snapshots(), TODAY_AFTER)
    assert nba_paper.summary(settled)["picks"] == 2
    champion = nba_paper.summary(settled, model_version=nba_paper.MODEL_VERSION)
    challenger = nba_paper.summary(settled, model_version="challenger")
    assert champion["record"] == "1-0"       # over pick, scored 30 vs 24.5
    assert challenger["record"] == "0-1"     # under pick lost


def test_rows_default_to_fanduel_points_and_can_carry_another_stat_and_book():
    (default,) = build([line()], {"Cade Cunningham": prediction()})
    assert (default["stat"], default["book"]) == ("points", "fanduel")
    (other,) = nba_paper.build_ledger_rows(
        EVENT, [line(point=8.5)], {"Cade Cunningham": prediction(mean=9.0)}, RECORDED_AT,
        GAME_DATE, stat="rebounds", book="kalshi")
    assert (other["stat"], other["book"]) == ("rebounds", "kalshi")


def test_the_same_player_can_have_several_lines_and_stats_recorded(tmp_path):
    path = tmp_path / "ledger.csv"
    points = build([line(point=24.5)], {"Cade Cunningham": prediction()})
    higher = build([line(point=29.5)], {"Cade Cunningham": prediction()})
    rebounds = nba_paper.build_ledger_rows(
        EVENT, [line(point=24.5)], {"Cade Cunningham": prediction()}, RECORDED_AT, GAME_DATE,
        stat="rebounds")
    assert nba_paper.append_rows(points, path) == 1
    assert nba_paper.append_rows(points, path) == 0                    # same line: a repeat
    assert nba_paper.append_rows(higher, path) == 1                    # another line is new
    assert nba_paper.append_rows(rebounds, path) == 1                  # another stat is new
    assert len(nba_paper.load_ledger(path)) == 3


def test_an_old_ledger_file_is_upgraded_before_new_rows_are_appended(tmp_path):
    path = tmp_path / "ledger.csv"
    old_columns = [c for c in nba_paper.COLUMNS if c not in ("stat", "book")]
    old_row = {c: None for c in old_columns} | {
        "event_id": "e0", "player": "Old Timer", "line": 20.5, "model_version": "ewma-v1",
        "status": "pending", "game_date": "2026-11-03", "player_id": 9}
    pd.DataFrame([old_row], columns=old_columns).to_csv(path, index=False)

    new = build([line()], {"Cade Cunningham": prediction()})
    assert nba_paper.append_rows(new, path) == 1

    ledger = nba_paper.load_ledger(path)
    assert len(ledger) == 2 and list(ledger.columns) == nba_paper.COLUMNS
    old = ledger[ledger["player"] == "Old Timer"].iloc[0]
    assert (old["stat"], old["book"]) == ("points", "fanduel")      # filled in for old rows
    assert path.read_text(encoding="utf-8").splitlines()[0].split(",") == nba_paper.COLUMNS


def test_each_stat_is_settled_from_its_own_box_score_column():
    rebounds = nba_paper.build_ledger_rows(
        EVENT, [line(point=8.5)], {"Cade Cunningham": prediction(mean=12.0)}, RECORDED_AT,
        GAME_DATE, stat="rebounds")
    games = pd.DataFrame({"player_id": [1], "game_date": pd.to_datetime([GAME_DATE]),
                          "pts": [30.0], "reb": [10.0]})
    settled = nba_paper.settle(ledger_with(rebounds), games, empty_snapshots(), TODAY_AFTER)
    assert settled["actual"].iloc[0] == 10.0                  # rebounds, not the 30 points
    assert bool(settled["went_over"].iloc[0]) is True


def test_a_stat_the_game_logs_dont_cover_is_left_pending_not_guessed():
    threes = nba_paper.build_ledger_rows(
        EVENT, [line(point=2.5)], {"Cade Cunningham": prediction(mean=3.0)}, RECORDED_AT,
        GAME_DATE, stat="threes")
    games = pd.DataFrame({"player_id": [1], "game_date": pd.to_datetime([GAME_DATE]),
                          "pts": [30.0]})                     # no fg3m column
    settled = nba_paper.settle(ledger_with(threes), games, empty_snapshots(), TODAY_AFTER)
    assert settled["status"].iloc[0] == "pending"


def test_summary_can_be_limited_to_one_stat_and_book():
    points = build([line()], {"Cade Cunningham": prediction(mean=32.0)})
    rebounds = nba_paper.build_ledger_rows(
        EVENT, [line(point=8.5)], {"Cade Cunningham": prediction(mean=14.0)}, RECORDED_AT,
        GAME_DATE, stat="rebounds", book="kalshi")
    ledger = ledger_with(points + rebounds)
    assert nba_paper.summary(ledger)["picks"] == 2
    assert nba_paper.summary(ledger, stat="rebounds")["picks"] == 1
    assert nba_paper.summary(ledger, book="fanduel")["picks"] == 1
    assert len(nba_paper.scope(ledger, stat="points", book="fanduel")) == 1


def comparison_frame():
    def row(version, player, p_model, went_over):
        return {"event_id": "e1", "player": player, "line": 24.5, "model_version": version,
                "status": "settled", "went_over": went_over,
                "model_p_over": p_model, "fair_p_over": 0.5}
    return pd.DataFrame([
        row("a", "p1", 1.0, 1), row("a", "p2", 0.0, 0), row("a", "p3", 1.0, 1),
        row("b", "p1", 0.5, 1), row("b", "p2", 0.5, 0),
    ])


def test_versions_are_compared_only_on_the_lines_they_share():
    table = nba_paper.compare_versions(comparison_frame())
    assert table.loc["a", "n"] == 2 and table.loc["b", "n"] == 2    # p3 is only in "a"
    assert table.loc["a", "brier_model"] == pytest.approx(0.0)
    assert table.loc["b", "brier_model"] == pytest.approx(0.25)
    assert table.loc["a", "brier_market"] == pytest.approx(0.25)
    assert table.loc["b", "brier_market"] == pytest.approx(0.25)


def test_comparing_with_a_single_version_gives_an_empty_table():
    only_a = comparison_frame().query("model_version == 'a'")
    assert nba_paper.compare_versions(only_a).empty


def test_calibration_with_no_settled_rows_is_empty_not_an_error():
    frame = pd.DataFrame({"status": ["pending"], "went_over": [None],
                          "model_p_over": [0.6], "fair_p_over": [0.5]})
    assert nba_paper.calibration_summary(frame)["n"] == 0
