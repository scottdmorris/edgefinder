"""Hand-verified checks on the X+ points (alternate line) ledger."""

import datetime as dt

import pandas as pd
import pytest

from edgefinder.tracking import nba_alt

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Boston Celtics", "away": "Milwaukee Bucks"}
TODAY = dt.date(2026, 11, 6)


def build(lines, model_p=None, monkeypatch=None, mean=26.0, version="ewma-v1"):
    if model_p is not None:
        monkeypatch.setattr(nba_alt, "p_at_least", lambda *_args: model_p)
    return nba_alt.build_alt_rows(
        EVENT, lines, {"A": {"player_id": 1, "mean": mean}}, "2026-11-04T17:00:00+00:00",
        "2026-11-04", model_version=version, dispersion=7.8)


def alt_line(point=14.5, odds=100, player="A"):
    return {"player": player, "line": point, "over_odds": odds}


def row(**overrides):
    base = {c: None for c in nba_alt.COLUMNS} | {
        "game_date": "2026-11-04", "event_id": "e1", "player": "A", "player_id": 1,
        "home": "Boston Celtics", "away": "Milwaukee Bucks",
        "threshold": 15, "over_odds": 100, "model_version": "ewma-v1", "model_mean": 26.0,
        "model_p": 0.6, "market_p": 0.5, "pick_ev": 0.06, "is_pick": True, "status": "pending"}
    return base | overrides


def frame(*rows):
    return pd.DataFrame(list(rows), columns=nba_alt.COLUMNS)


def games(pts, day="2026-11-04"):
    return pd.DataFrame({"player_id": [1], "game_date": pd.to_datetime([day]), "pts": [pts]})


# ---- pick rule ------------------------------------------------------------------------------

@pytest.mark.parametrize("ev, model_p, market_p, expected", [
    (0.02, 0.50, 0.40, True),     # EV exactly at the bar
    (0.0199, 0.50, 0.40, False),  # a hair under
    (0.10, 0.35, 0.30, True),     # model chance exactly at the 35% floor
    (0.10, 0.34, 0.30, False),    # under it: the model's tail is not trusted
    (0.10, 0.50, 0.375, True),    # 12.5 points of disagreement is fine
    (0.10, 0.50, 0.30, False),    # 20 points of disagreement is a data problem
    (0.10, 0.30, 0.50, False),    # disagreement is symmetric, and 0.30 is under the floor anyway
    (-0.05, 0.60, 0.55, False),
])
def test_pick_rule(ev, model_p, market_p, expected):
    assert nba_alt.is_pick(ev, model_p, market_p) is expected


# ---- probabilities -----------------------------------------------------------------------------

def test_at_least_one_with_ten_over_ten_is_hand_computable():
    # negative binomial, mean 10, dispersion 10: P(0) = (10/20)^10 = 1/1024
    assert nba_alt.p_at_least(1, 10.0, 10.0) == pytest.approx(1 - 1 / 1024)


def test_at_least_zero_is_certain():
    assert nba_alt.p_at_least(0, 15.0, 7.8) == pytest.approx(1.0)


@pytest.mark.parametrize("prob, american", [
    (0.5, -100), (0.25, 300), (0.75, -300), (0.2, 400), (0.8, -400)])
def test_fair_american_hand_values(prob, american):
    assert nba_alt.fair_american(prob) == american


def test_fair_american_clamps_certainties():
    assert nba_alt.fair_american(0.0) == 99900
    assert nba_alt.fair_american(1.0) == -99900


def test_chances_from_the_ladder_are_probabilities_that_fall_with_the_rung():
    table = nba_alt.ladder({"ewma-v1": 22.0})
    chances = table["ewma-v1 chance %"].tolist()
    assert all(0.0 <= c <= 100.0 for c in chances)
    assert chances == sorted(chances, reverse=True)
    assert list(table["Points"]) == [f"{r}+" for r in nba_alt.RUNGS]


def test_ladder_prices_each_model_with_its_own_spread():
    table = nba_alt.ladder({"ewma-v1": 20.0, "minutes-v1": 20.0}, rungs=[20])
    assert {"ewma-v1 chance %", "ewma-v1 fair odds",
            "minutes-v1 chance %", "minutes-v1 fair odds"} <= set(table.columns)


def test_ladder_fair_odds_agree_with_the_chance_shown():
    table = nba_alt.ladder({"ewma-v1": 22.0}, rungs=[10, 20, 30])
    for chance, odds in zip(table["ewma-v1 chance %"], table["ewma-v1 fair odds"]):
        implied = -odds / (-odds + 100.0) if odds < 0 else 100.0 / (odds + 100.0)
        assert implied == pytest.approx(chance / 100.0, abs=0.01)


def test_player_means_lists_each_models_projection_once():
    ledger = frame(row(model_version="ewma-v1", model_mean=20.0),
                   row(model_version="ewma-v1", model_mean=20.0, threshold=20),
                   row(model_version="minutes-v1", model_mean=22.5),
                   row(player="B", model_mean=5.0))
    assert nba_alt.player_means(ledger, "2026-11-04", "A") == {"ewma-v1": 20.0,
                                                               "minutes-v1": 22.5}
    assert nba_alt.player_means(ledger, "2026-11-09", "A") == {}


# ---- building rows --------------------------------------------------------------------------------

def test_a_pick_row_by_hand(monkeypatch):
    # +100 -> market 0.5 ; model 0.6 ; blend 0.3*0.6 + 0.7*0.5 = 0.53 ; EV = 0.53*1 - 0.47 = 0.06
    result = build([alt_line(14.5, 100)], 0.6, monkeypatch)[0]
    assert result["threshold"] == 15                  # 14.5 means 15+
    assert result["market_p"] == pytest.approx(0.5)
    assert result["is_pick"] is True and result["pick_ev"] == pytest.approx(0.06)


def test_a_big_disagreement_is_recorded_but_not_picked(monkeypatch):
    # model 0.8 vs market 0.5: 30 points apart -> excluded as a data problem
    result = build([alt_line(14.5, 100)], 0.8, monkeypatch)[0]
    assert result["is_pick"] is False and result["pick_ev"] is None


def test_a_negative_edge_is_recorded_but_not_picked(monkeypatch):
    # model 0.4 vs market 0.5: blend 0.47, EV = 0.47 - 0.53 = -0.06
    result = build([alt_line(14.5, 100)], 0.4, monkeypatch)[0]
    assert result["is_pick"] is False and result["pick_ev"] is None


def test_market_probability_keeps_the_vig(monkeypatch):
    # -130 -> 130/230 = 0.5652: not devigged, deliberately conservative
    result = build([alt_line(14.5, -130)], 0.6, monkeypatch)[0]
    assert result["market_p"] == pytest.approx(130 / 230)


def test_whole_number_and_unpriced_and_unprojected_lines_are_skipped():
    lines = [alt_line(15.0), alt_line(14.5, None), alt_line(14.5, 100, player="Nobody")]
    assert build(lines) == []


def test_the_threshold_is_the_next_whole_number():
    rows = build([alt_line(14.5), alt_line(24.5)])
    assert [r["threshold"] for r in rows] == [15, 25]


# ---- idempotent append ---------------------------------------------------------------------------------

def test_append_is_idempotent_on_event_player_threshold_model(tmp_path):
    path = tmp_path / "alt.csv"
    rows = build([alt_line(14.5), alt_line(19.5)])
    assert nba_alt.append_rows(rows, path) == 2
    assert nba_alt.append_rows(rows, path) == 0
    assert len(nba_alt.load_ledger(path)) == 2


def test_append_ignores_duplicates_inside_one_batch(tmp_path):
    path = tmp_path / "alt.csv"
    one = build([alt_line()])[0]
    assert nba_alt.append_rows([one, dict(one)], path) == 1


@pytest.mark.parametrize("change", [{"model_version": "minutes-v1"}, {"threshold": 20},
                                    {"player": "B"}, {"event_id": "e2"}])
def test_any_changed_key_part_is_a_new_row(tmp_path, change):
    path = tmp_path / "alt.csv"
    base = build([alt_line()])[0]
    nba_alt.append_rows([base], path)
    assert nba_alt.append_rows([base | change], path) == 1


def test_missing_file_loads_empty_and_nothing_new_writes_no_file(tmp_path):
    path = tmp_path / "alt.csv"
    assert nba_alt.load_ledger(path).empty
    assert nba_alt.append_rows([], path) == 0
    assert not path.exists()


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "sub" / "alt.csv"
    nba_alt.save_ledger(frame(row()), path)
    assert nba_alt.load_ledger(path).loc[0, "threshold"] == 15


# ---- recording an event ----------------------------------------------------------------------------------

class FakeModel:
    def __init__(self, version, fail=False):
        self.version, self.dispersion, self.fail = version, 7.8, fail

    def project(self, event, names):
        if self.fail:
            raise RuntimeError("model blew up")
        return {name: {"player_id": 1, "mean": 25.0} for name in names}


def test_one_failing_model_does_not_stop_the_others(tmp_path):
    path = tmp_path / "alt.csv"
    added = nba_alt.record_event(
        EVENT, [alt_line(14.5)], [FakeModel("bad", fail=True), FakeModel("good")],
        "2026-11-04T17:00:00+00:00", "2026-11-04", path=path)
    assert added == {"bad": 0, "good": 1}
    assert set(nba_alt.load_ledger(path)["model_version"]) == {"good"}


def test_recording_twice_adds_nothing_the_second_time(tmp_path):
    path = tmp_path / "alt.csv"
    args = (EVENT, [alt_line(14.5)], [FakeModel("m")], "2026-11-04T17:00:00+00:00", "2026-11-04")
    assert nba_alt.record_event(*args, path=path) == {"m": 1}
    assert nba_alt.record_event(*args, path=path) == {"m": 0}


def test_games_recorded_counts_distinct_events_on_a_date():
    ledger = frame(row(), row(threshold=20), row(event_id="e2"), row(event_id="e3",
                                                                      game_date="2026-11-05"))
    assert nba_alt.games_recorded(ledger, "2026-11-04") == 2
    assert nba_alt.games_recorded(ledger, "2026-12-01") == 0


# ---- settlement -------------------------------------------------------------------------------------------------

def test_exactly_the_threshold_wins():
    out = nba_alt.settle(frame(row(threshold=15, over_odds=150)), games(15), TODAY)
    assert out.loc[0, "result"] == "win" and out.loc[0, "pnl_units"] == pytest.approx(1.5)
    assert out.loc[0, "actual"] == 15


def test_one_short_of_the_threshold_loses_a_unit():
    out = nba_alt.settle(frame(row(threshold=15)), games(14), TODAY)
    assert out.loc[0, "result"] == "loss" and out.loc[0, "pnl_units"] == -1.0


def test_winning_at_minus_200_pays_half_a_unit():
    out = nba_alt.settle(frame(row(over_odds=-200)), games(30), TODAY)
    assert out.loc[0, "pnl_units"] == pytest.approx(0.5)


def test_non_picks_are_settled_without_a_result():
    out = nba_alt.settle(frame(row(is_pick=False, pick_ev=None)), games(30), TODAY)
    assert out.loc[0, "status"] == "settled" and out.loc[0, "actual"] == 30
    assert pd.isna(out.loc[0, "result"]) and pd.isna(out.loc[0, "pnl_units"])


def test_a_past_game_with_no_box_score_is_void():
    out = nba_alt.settle(frame(row()), games(30).iloc[0:0], TODAY)
    assert out.loc[0, "status"] == "void" and out.loc[0, "pnl_units"] == 0.0


def test_today_or_future_game_without_a_box_score_stays_pending():
    out = nba_alt.settle(frame(row(game_date="2026-11-06")), games(30).iloc[0:0], TODAY)
    assert out.loc[0, "status"] == "pending"


def test_settled_rows_are_left_alone_and_input_is_not_mutated():
    original = frame(row(), row(player="B", status="settled", result="loss", pnl_units=-1.0))
    out = nba_alt.settle(original, games(30), TODAY)
    assert original.loc[0, "status"] == "pending"
    assert out.loc[1, "result"] == "loss"


# ---- summary and suggestions ------------------------------------------------------------------------------------

def test_summary_by_hand():
    ledger = frame(
        row(status="settled", result="win", pnl_units=1.5),
        row(player="B", status="settled", result="loss", pnl_units=-1.0),
        row(player="C", status="settled", result="loss", pnl_units=-1.0),
        row(player="D", is_pick=False, status="settled"),     # not a pick
        row(player="E"),                                        # pick, still pending
        row(player="F", model_version="minutes-v1", status="settled", result="win",
            pnl_units=2.0))
    everything = nba_alt.summary(ledger)
    assert everything["picks"] == 5 and everything["settled"] == 4
    assert everything["record"] == "2-2" and everything["units"] == pytest.approx(1.5)
    assert everything["roi_pct"] == pytest.approx(37.5)        # 1.5 over 4 bets
    one_model = nba_alt.summary(ledger, model_version="minutes-v1")
    assert one_model["picks"] == 1 and one_model["units"] == pytest.approx(2.0)
    assert one_model["roi_pct"] == pytest.approx(200.0)


def test_summary_with_no_settled_picks_has_zero_roi():
    s = nba_alt.summary(frame(row()))
    assert s["settled"] == 0 and s["roi_pct"] == 0.0 and s["record"] == "0-0"


def test_suggestions_are_empty_when_the_day_has_no_picks():
    assert nba_alt.suggestions(frame(row(is_pick=False)), "2026-11-04").empty
    assert nba_alt.suggestions(frame(row()), "2026-12-25").empty


def test_models_that_agree_are_merged_and_counted():
    ledger = frame(row(model_version="ewma-v1", pick_ev=0.05),
                   row(model_version="minutes-v1", pick_ev=0.09),
                   row(player="B", model_version="ewma-v1", pick_ev=0.20))
    table = nba_alt.suggestions(ledger, "2026-11-04")
    by_bet = table.set_index("Bet")
    assert by_bet.loc["A · 15+ points", "Agree"] == 2
    assert by_bet.loc["A · 15+ points", "EV %"] == pytest.approx(9.0)    # the better EV of the two
    assert by_bet.loc["B · 15+ points", "Agree"] == 1


def test_agreement_ranks_ahead_of_raw_value():
    ledger = frame(row(model_version="ewma-v1", pick_ev=0.05),
                   row(model_version="minutes-v1", pick_ev=0.05),
                   row(player="B", pick_ev=0.40))
    assert nba_alt.suggestions(ledger, "2026-11-04")["Bet"].tolist()[0] == "A · 15+ points"


def test_neighbouring_rungs_for_one_player_keep_only_the_best():
    ledger = frame(row(threshold=14, pick_ev=0.03), row(threshold=15, pick_ev=0.08),
                   row(threshold=16, pick_ev=0.05))
    table = nba_alt.suggestions(ledger, "2026-11-04")
    assert table["Bet"].tolist() == ["A · 15+ points"]


def test_suggestions_are_capped_at_top():
    ledger = frame(*[row(player=f"P{i}", pick_ev=0.02 + i / 100) for i in range(6)])
    table = nba_alt.suggestions(ledger, "2026-11-04", top=3)
    assert len(table) == 3
    assert table["EV %"].tolist() == sorted(table["EV %"].tolist(), reverse=True)
