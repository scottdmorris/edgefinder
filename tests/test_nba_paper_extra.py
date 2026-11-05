"""Hand-verified checks on the NBA paper ledger: pricing, idempotent append,
settlement, closing-line value and scoring."""

import datetime as dt

import pandas as pd
import pytest

from edgefinder.betting.odds_math import american_to_decimal
from edgefinder.tracking import nba_paper

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
TODAY = dt.date(2026, 11, 6)


def line(player="A", point=24.5, over=-110, under=-110):
    return {"player": player, "line": point, "over_odds": over, "under_odds": under}


def build(lines, predictions=None, **kwargs):
    predictions = predictions or {"A": {"player_id": 1, "mean": 25.0}}
    return nba_paper.build_ledger_rows(EVENT, lines, predictions, "2026-11-04T17:00:00+00:00",
                                       "2026-11-04", **kwargs)


def row(**overrides):
    base = {c: None for c in nba_paper.COLUMNS} | {
        "game_date": "2026-11-04", "event_id": "e1", "commence_time": EVENT["commence_time"],
        "player": "A", "player_id": 1, "line": 24.5, "over_odds": -110, "under_odds": -110,
        "model_version": "v1", "model_p_over": 0.6, "fair_p_over": 0.5,
        "status": "pending", "stat": "points", "book": "fanduel"}
    return base | overrides


def frame(*rows):
    return pd.DataFrame(list(rows), columns=nba_paper.COLUMNS)


def games(pts=None, reb=None, day="2026-11-04"):
    data = {"player_id": [1], "game_date": pd.to_datetime([day])}
    if pts is not None:
        data["pts"] = [pts]
    if reb is not None:
        data["reb"] = [reb]
    return pd.DataFrame(data)


NO_SNAPSHOTS = pd.DataFrame(columns=["fetched_at", "phase", "event_id", "player", "line",
                                     "over_odds", "under_odds"])


def snapshots(*rows):
    return pd.DataFrame(list(rows), columns=NO_SNAPSHOTS.columns)


def late(line_=24.5, over=-130, under=100, fetched="2026-11-04T23:00:00", player="A", event="e1"):
    return (fetched, "late", event, player, line_, over, under)


@pytest.fixture
def fixed_model(monkeypatch):
    """Pin the model's P(over) so the blend can be worked out by hand."""
    def set_p(value):
        monkeypatch.setattr(nba_paper.negbin, "over_prob", lambda *_args: value)
    return set_p


# ---- pricing a line ---------------------------------------------------------------------

def test_over_pick_blend_and_ev_by_hand(fixed_model):
    fixed_model(0.8)
    # fair over 0.5 ; blend = 0.3*0.8 + 0.7*0.5 = 0.59 ; at -110 (21/11):
    # EV over = 0.59*(10/11) - 0.41 = 0.126364 ; EV under = 0.41*(10/11) - 0.59 < 0
    result = build([line()])[0]
    assert result["pick_side"] == "over"
    assert result["pick_odds"] == -110
    assert result["pick_ev"] == pytest.approx(0.59 * 10 / 11 - 0.41)
    assert result["fair_p_over"] == pytest.approx(0.5)
    assert result["model_p_over"] == pytest.approx(0.8)


def test_under_pick_mirrors_the_over(fixed_model):
    fixed_model(0.2)
    # blend over = 0.3*0.2 + 0.35 = 0.41 ; EV under = 0.59*(10/11) - 0.41
    result = build([line(under=-110)])[0]
    assert result["pick_side"] == "under"
    assert result["pick_ev"] == pytest.approx(0.59 * 10 / 11 - 0.41)


def test_the_pick_threshold_is_two_percent_ev(fixed_model):
    # at -110/-110, EV over = (21/11)*blend - 1 ; blend = 0.35 + 0.3*m
    fixed_model(0.60)   # blend 0.53 -> EV 0.0118: below the bar
    below = build([line()])[0]
    assert below["pick_side"] is None and below["pick_ev"] is None and below["pick_odds"] is None
    fixed_model(0.63)   # blend 0.539 -> EV 0.0291: above it
    above = build([line()])[0]
    assert above["pick_side"] == "over"
    assert above["pick_ev"] == pytest.approx((21 / 11) * 0.539 - 1)


def test_an_unpicked_line_is_still_logged_for_calibration(fixed_model):
    fixed_model(0.5)
    result = build([line()])[0]
    assert result["pick_side"] is None
    assert result["status"] == "pending"
    assert result["model_p_over"] == pytest.approx(0.5)


def test_whole_number_lines_are_skipped_because_a_push_would_refund():
    assert build([line(point=24.0)]) == []


def test_stat_book_and_version_are_recorded():
    result = build([line()], stat="rebounds", book="draftkings", model_version="v9")[0]
    assert (result["stat"], result["book"], result["model_version"]) == (
        "rebounds", "draftkings", "v9")


def test_every_ledger_column_is_present_in_a_new_row():
    assert set(build([line()])[0]) == set(nba_paper.COLUMNS)


# ---- idempotent append -------------------------------------------------------------------

def test_append_is_idempotent_on_the_row_key(tmp_path):
    path = tmp_path / "log.csv"
    rows = build([line(), line(point=25.5)])
    assert nba_paper.append_rows(rows, path) == 2
    assert nba_paper.append_rows(rows, path) == 0
    assert len(nba_paper.load_ledger(path)) == 2


def test_append_repeated_n_times_writes_each_row_once(tmp_path):
    path = tmp_path / "log.csv"
    rows = build([line()])
    for _ in range(5):
        nba_paper.append_rows(rows, path)
    assert len(nba_paper.load_ledger(path)) == 1


def test_a_batch_with_internal_duplicates_is_written_once(tmp_path):
    path = tmp_path / "log.csv"
    one = build([line()])[0]
    assert nba_paper.append_rows([one, dict(one)], path) == 1


@pytest.mark.parametrize("change", [
    {"model_version": "v2"}, {"stat": "rebounds"}, {"book": "draftkings"},
    {"player": "B"}, {"line": 25.5}, {"event_id": "e2"}])
def test_a_different_key_part_is_a_new_row(tmp_path, change):
    path = tmp_path / "log.csv"
    base = build([line()])[0]
    nba_paper.append_rows([base], path)
    assert nba_paper.append_rows([base | change], path) == 1


def test_append_with_nothing_new_does_not_create_the_file(tmp_path):
    path = tmp_path / "log.csv"
    assert nba_paper.append_rows([], path) == 0
    assert not path.exists()


def test_append_creates_missing_folders_and_a_header(tmp_path):
    path = tmp_path / "deep" / "log.csv"
    nba_paper.append_rows(build([line()]), path)
    assert path.read_text(encoding="utf-8").splitlines()[0].split(",") == nba_paper.COLUMNS


def test_old_ledger_without_stat_and_book_is_upgraded_before_appending(tmp_path):
    path = tmp_path / "log.csv"
    old_columns = [c for c in nba_paper.COLUMNS if c not in ("stat", "book")]
    old = pd.DataFrame([row()], columns=nba_paper.COLUMNS)[old_columns]
    old.to_csv(path, index=False)
    assert nba_paper.append_rows(build([line(player="Z")], {"Z": {"player_id": 9, "mean": 20}}),
                                 path) == 1
    reloaded = nba_paper.load_ledger(path)
    assert len(reloaded) == 2
    assert list(pd.read_csv(path).columns) == nba_paper.COLUMNS
    assert set(reloaded["stat"]) == {"points"} and set(reloaded["book"]) == {"fanduel"}


def test_legacy_rows_dedupe_against_new_rows_as_points_at_fanduel(tmp_path):
    path = tmp_path / "log.csv"
    legacy = pd.DataFrame([row()], columns=nba_paper.COLUMNS).drop(columns=["stat", "book"])
    legacy.to_csv(path, index=False)
    same = build([line()], {"A": {"player_id": 1, "mean": 25.0}}, model_version="v1")
    assert nba_paper.append_rows(same, path) == 0


def test_missing_ledger_file_loads_as_an_empty_typed_frame(tmp_path):
    empty = nba_paper.load_ledger(tmp_path / "nope.csv")
    assert list(empty.columns) == nba_paper.COLUMNS and empty.empty


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "x" / "log.csv"
    nba_paper.save_ledger(frame(row()), path)
    loaded = nba_paper.load_ledger(path)
    assert loaded.loc[0, "line"] == 24.5 and loaded.loc[0, "player"] == "A"


@pytest.mark.xfail(strict=True, reason=(
    "BUG (latent): append_rows dedupes on a key built from event_id as written, but "
    "load_ledger lets pandas infer dtypes, so an all-digit event_id comes back as an int. "
    "('20261104', ...) != (20261104, ...), so the same row is appended AGAIN on every run. "
    "Odds API ids are normally 32 hex chars, so this only bites on a digit-only id."))
def test_append_is_idempotent_even_for_a_digit_only_event_id(tmp_path):
    path = tmp_path / "log.csv"
    numeric = row(event_id="20261104")
    nba_paper.append_rows([numeric], path)
    assert nba_paper.append_rows([numeric], path) == 0


# ---- settlement --------------------------------------------------------------------------------

def test_winning_over_pays_the_decimal_profit():
    pick = row(pick_side="over", pick_odds=150)             # +150 -> profit 1.5
    out = nba_paper.settle(frame(pick), games(pts=30), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "result"] == "win" and out.loc[0, "pnl_units"] == pytest.approx(1.5)
    assert out.loc[0, "status"] == "settled" and out.loc[0, "actual"] == 30
    assert bool(out.loc[0, "went_over"]) is True


def test_losing_over_costs_one_unit():
    pick = row(pick_side="over", pick_odds=-110)
    out = nba_paper.settle(frame(pick), games(pts=20), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "result"] == "loss" and out.loc[0, "pnl_units"] == -1.0


def test_winning_under_at_minus_110_pays_ten_elevenths():
    pick = row(pick_side="under", pick_odds=-110)
    out = nba_paper.settle(frame(pick), games(pts=20), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "result"] == "win"
    assert out.loc[0, "pnl_units"] == pytest.approx(10 / 11)


def test_losing_under_costs_one_unit():
    pick = row(pick_side="under", pick_odds=-110)
    out = nba_paper.settle(frame(pick), games(pts=25), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "result"] == "loss" and out.loc[0, "pnl_units"] == -1.0


def test_exactly_at_the_next_whole_number_clears_a_half_point_line():
    # line 24.5: 25 beats it, 24 does not
    over = row(pick_side="over", pick_odds=100)
    assert nba_paper.settle(frame(over), games(pts=25), NO_SNAPSHOTS, TODAY).loc[0, "result"] == "win"
    assert nba_paper.settle(frame(over), games(pts=24), NO_SNAPSHOTS, TODAY).loc[0, "result"] == "loss"


def test_an_unpicked_line_is_settled_for_calibration_without_pnl():
    out = nba_paper.settle(frame(row()), games(pts=30), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "status"] == "settled" and bool(out.loc[0, "went_over"]) is True
    assert pd.isna(out.loc[0, "result"]) and pd.isna(out.loc[0, "pnl_units"])


def test_settling_does_not_mutate_the_input_ledger():
    original = frame(row(pick_side="over", pick_odds=100))
    nba_paper.settle(original, games(pts=30), NO_SNAPSHOTS, TODAY)
    assert original.loc[0, "status"] == "pending"


def test_a_player_who_did_not_play_on_a_past_date_is_voided():
    out = nba_paper.settle(frame(row(pick_side="over", pick_odds=100)), games(pts=30).iloc[0:0],
                           NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "status"] == "void" and out.loc[0, "pnl_units"] == 0.0


def test_a_missing_box_score_for_today_stays_pending():
    today_row = row(game_date="2026-11-06")
    out = nba_paper.settle(frame(today_row), games(pts=30).iloc[0:0], NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "status"] == "pending"


def test_other_stats_settle_from_their_own_column():
    rebounds = row(stat="rebounds", line=9.5, pick_side="over", pick_odds=100)
    out = nba_paper.settle(frame(rebounds), games(pts=40, reb=12), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "actual"] == 12 and out.loc[0, "result"] == "win"
    out = nba_paper.settle(frame(rebounds), games(pts=40, reb=9), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "result"] == "loss"       # 40 points must NOT be read as the rebound count


def test_a_stat_the_game_logs_do_not_cover_is_left_pending_not_voided():
    rebounds = row(stat="rebounds", line=9.5, pick_side="over", pick_odds=100)
    out = nba_paper.settle(frame(rebounds), games(pts=40), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "status"] == "pending"


def test_already_settled_rows_are_not_touched_again():
    done = row(status="settled", actual=11.0, pick_side="over", pick_odds=100, result="loss",
               pnl_units=-1.0)
    out = nba_paper.settle(frame(done), games(pts=30), NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "result"] == "loss" and out.loc[0, "actual"] == 11.0


def test_settlement_is_idempotent():
    pick = frame(row(pick_side="over", pick_odds=150))
    once = nba_paper.settle(pick, games(pts=30), NO_SNAPSHOTS, TODAY)
    twice = nba_paper.settle(once, games(pts=30), NO_SNAPSHOTS, TODAY)
    assert twice.loc[0, "pnl_units"] == once.loc[0, "pnl_units"] == pytest.approx(1.5)


# ---- closing-line value --------------------------------------------------------------------------

def test_clv_is_the_gain_in_implied_probability_when_the_line_held():
    pick = row(pick_side="over", pick_odds=-110)
    out = nba_paper.settle(frame(pick), games(pts=30), snapshots(late(over=-130)), TODAY)
    # placed 110/210 ; closed 130/230 ; (130*210)/(230*110) - 1 = 27300/25300 - 1 = 7.9051%
    assert out.loc[0, "clv_pct"] == pytest.approx(2000 / 25300 * 100.0)
    assert out.loc[0, "line_move"] == 0.0
    assert out.loc[0, "closing_line"] == 24.5 and out.loc[0, "closing_over_odds"] == -130


def test_clv_is_negative_when_the_price_got_worse():
    pick = row(pick_side="over", pick_odds=-130)
    out = nba_paper.settle(frame(pick), games(pts=30), snapshots(late(over=-110)), TODAY)
    assert out.loc[0, "clv_pct"] < 0
    assert out.loc[0, "clv_pct"] == pytest.approx((110 / 210 - 130 / 230) / (130 / 230) * 100.0)


def test_under_picks_use_the_closing_under_price():
    pick = row(pick_side="under", pick_odds=100)
    out = nba_paper.settle(frame(pick), games(pts=20), snapshots(late(under=-120)), TODAY)
    # placed 0.5 ; closed 120/220 = 0.54545 ; (0.54545 - 0.5)/0.5 = 9.0909%
    assert out.loc[0, "clv_pct"] == pytest.approx(10 / 110 * 100.0)


def test_line_movement_in_the_picks_favour_is_positive_for_an_over():
    pick = row(pick_side="over", pick_odds=-110, line=24.5)
    out = nba_paper.settle(frame(pick), games(pts=30), snapshots(late(line_=25.5)), TODAY)
    assert out.loc[0, "line_move"] == 1.0           # the market now needs more than you did
    assert pd.isna(out.loc[0, "clv_pct"])           # prices at different lines don't compare


def test_line_movement_in_the_picks_favour_is_positive_for_an_under():
    pick = row(pick_side="under", pick_odds=-110, line=24.5)
    out = nba_paper.settle(frame(pick), games(pts=20), snapshots(late(line_=23.5)), TODAY)
    assert out.loc[0, "line_move"] == 1.0           # you took 24.5 and it closed at 23.5


def test_line_movement_against_the_pick_is_negative():
    over = row(pick_side="over", pick_odds=-110, line=24.5)
    out = nba_paper.settle(frame(over), games(pts=30), snapshots(late(line_=23.5)), TODAY)
    assert out.loc[0, "line_move"] == -1.0


def test_clv_needs_a_closing_price_for_the_picked_side():
    pick = row(pick_side="over", pick_odds=-110)
    out = nba_paper.settle(frame(pick), games(pts=30), snapshots(late(over=None)), TODAY)
    assert pd.isna(out.loc[0, "clv_pct"])


def test_the_last_late_snapshot_is_the_closing_line():
    pick = row(pick_side="over", pick_odds=-110)
    snaps = snapshots(late(over=-150, fetched="2026-11-04T22:30:00"),
                      late(over=-120, fetched="2026-11-04T23:30:00"))
    out = nba_paper.settle(frame(pick), games(pts=30), snaps, TODAY)
    assert out.loc[0, "closing_over_odds"] == -120


def test_early_snapshots_never_count_as_closing():
    pick = row(pick_side="over", pick_odds=-110)
    early = snapshots(("2026-11-04T17:00:00", "early", "e1", "A", 24.5, -300, 250))
    out = nba_paper.settle(frame(pick), games(pts=30), early, TODAY)
    assert pd.isna(out.loc[0, "closing_line"])


def test_an_unpicked_line_gets_closing_info_but_no_movement():
    out = nba_paper.settle(frame(row()), games(pts=30), snapshots(late(line_=25.5)), TODAY)
    assert out.loc[0, "closing_line"] == 25.5
    assert pd.isna(out.loc[0, "line_move"]) and pd.isna(out.loc[0, "clv_pct"])


def test_no_closing_snapshot_for_that_player_leaves_the_row_alone():
    pick = row(pick_side="over", pick_odds=-110)
    out = nba_paper.settle(frame(pick), games(pts=30), snapshots(late(player="Someone Else")), TODAY)
    assert pd.isna(out.loc[0, "closing_line"])


@pytest.mark.parametrize("change", [{"stat": "rebounds"}, {"book": "draftkings"}])
def test_only_fanduel_points_rows_are_closed_against_the_fanduel_points_snapshots(change):
    pick = row(pick_side="over", pick_odds=-110, **change)
    out = nba_paper.settle(frame(pick), games(pts=30, reb=30), snapshots(late()), TODAY)
    assert pd.isna(out.loc[0, "closing_line"])


def test_pending_rows_are_not_closed():
    pending = row(pick_side="over", pick_odds=-110, game_date="2026-11-06")
    out = nba_paper.settle(frame(pending), games(pts=30).iloc[0:0], snapshots(late()), TODAY)
    assert out.loc[0, "status"] == "pending" and pd.isna(out.loc[0, "closing_line"])


# ---- scoring ---------------------------------------------------------------------------------------

def settled_frame():
    return frame(
        row(player="A", pick_side="over", pick_odds=150, status="settled", result="win",
            pnl_units=1.5, clv_pct=4.0, line_move=1.0, model_p_over=0.8, fair_p_over=0.5,
            went_over=True),
        row(player="B", pick_side="under", pick_odds=-110, status="settled", result="loss",
            pnl_units=-1.0, clv_pct=-2.0, line_move=-0.5, model_p_over=0.3, fair_p_over=0.5,
            went_over=True),
        row(player="C", status="settled", model_p_over=0.9, fair_p_over=0.5, went_over=True),
        row(player="D", pick_side="over", pick_odds=100, status="pending"),
    )


def test_summary_counts_units_roi_and_averages_by_hand():
    s = nba_paper.summary(settled_frame())
    assert s["picks"] == 3 and s["settled"] == 2          # C is not a pick; D is not settled
    assert s["record"] == "1-1"
    assert s["units"] == pytest.approx(0.5)               # +1.5 - 1.0
    assert s["roi_pct"] == pytest.approx(25.0)            # 0.5 units over 2 settled picks
    assert s["avg_clv_pct"] == pytest.approx(1.0)         # (4 - 2) / 2
    assert s["avg_line_move"] == pytest.approx(0.25)      # (1.0 - 0.5) / 2


def test_summary_of_an_empty_ledger_is_all_zeros_and_none():
    s = nba_paper.summary(frame())
    assert s["picks"] == 0 and s["settled"] == 0 and s["record"] == "0-0"
    assert s["units"] == 0.0 and s["roi_pct"] == 0.0
    assert s["avg_clv_pct"] is None and s["avg_line_move"] is None


def test_scope_filters_by_each_dimension():
    ledger = frame(row(model_version="v1"), row(model_version="v2", player="B"),
                   row(stat="rebounds", player="C"), row(book="draftkings", player="D"))
    assert len(nba_paper.scope(ledger)) == 4
    assert len(nba_paper.scope(ledger, model_version="v2")) == 1
    assert len(nba_paper.scope(ledger, stat="rebounds")) == 1
    assert len(nba_paper.scope(ledger, book="draftkings")) == 1
    assert len(nba_paper.scope(ledger, model_version="v1", stat="points", book="fanduel")) == 1


def test_summary_respects_the_model_filter():
    ledger = frame(
        row(pick_side="over", pick_odds=100, status="settled", result="win", pnl_units=1.0),
        row(model_version="v2", player="B", pick_side="over", pick_odds=100, status="settled",
            result="loss", pnl_units=-1.0))
    assert nba_paper.summary(ledger, model_version="v2")["units"] == -1.0
    assert nba_paper.summary(ledger, model_version="v1")["units"] == 1.0


def test_brier_scores_by_hand():
    # model: (0.8-1)^2 = 0.04, (0.3-1)^2 = 0.49, (0.9-1)^2 = 0.01 -> mean 0.18
    # market: 0.25 each -> 0.25
    c = nba_paper.calibration_summary(settled_frame())
    assert c["n"] == 3
    assert c["brier_model"] == pytest.approx(0.18)
    assert c["brier_market"] == pytest.approx(0.25)


def test_brier_scores_are_bounded_between_zero_and_one():
    c = nba_paper.calibration_summary(settled_frame())
    assert 0.0 <= c["brier_model"] <= 1.0 and 0.0 <= c["brier_market"] <= 1.0


def test_calibration_with_nothing_settled_is_empty():
    c = nba_paper.calibration_summary(frame(row()))
    assert c == {"n": 0, "brier_model": None, "brier_market": None}


def test_compare_versions_scores_only_lines_every_model_priced():
    ledger = frame(
        row(model_version="v1", player="A", status="settled", went_over=True,
            model_p_over=0.8, fair_p_over=0.5),
        row(model_version="v2", player="A", status="settled", went_over=True,
            model_p_over=0.6, fair_p_over=0.5),
        # only v1 priced B: it must not flatter or penalise v1
        row(model_version="v1", player="B", status="settled", went_over=False,
            model_p_over=0.9, fair_p_over=0.5))
    table = nba_paper.compare_versions(ledger)
    assert table.loc["v1", "n"] == 1 and table.loc["v2", "n"] == 1
    assert table.loc["v1", "brier_model"] == pytest.approx(0.04)     # (0.8 - 1)^2
    assert table.loc["v2", "brier_model"] == pytest.approx(0.16)     # (0.6 - 1)^2
    assert table.loc["v1", "brier_market"] == pytest.approx(0.25)


def test_compare_versions_needs_two_models():
    ledger = frame(row(status="settled", went_over=True))
    assert nba_paper.compare_versions(ledger).empty


def test_compare_versions_is_empty_when_no_line_was_priced_by_all():
    ledger = frame(
        row(model_version="v1", player="A", status="settled", went_over=True),
        row(model_version="v2", player="B", status="settled", went_over=False))
    assert nba_paper.compare_versions(ledger).empty


@pytest.mark.parametrize("odds, profit", [(-250, 0.4), (-110, 10 / 11), (100, 1.0), (180, 1.8)])
def test_winning_profit_per_unit_at_each_price(odds, profit):
    # -250: win 100 on 250 -> 0.4 ; +180: win 180 on 100 -> 1.8
    out = nba_paper.settle(frame(row(pick_side="over", pick_odds=odds)), games(pts=30),
                           NO_SNAPSHOTS, TODAY)
    assert out.loc[0, "pnl_units"] == pytest.approx(profit)
    assert american_to_decimal(odds) - 1.0 == pytest.approx(profit)
