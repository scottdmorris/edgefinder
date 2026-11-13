import datetime as dt

import pandas as pd
import pytest

from edgefinder.data import nba_props
from edgefinder.tracking import nba_alt

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Boston Celtics", "away": "Milwaukee Bucks"}
LINES = [
    {"player": "Jaylen Brown", "line": 14.5, "over_odds": -1000},
    {"player": "Jaylen Brown", "line": 24.5, "over_odds": 130},
    {"player": "Jaylen Brown", "line": 30.0, "over_odds": 400},   # whole number: skipped
    {"player": "Nobody Known", "line": 9.5, "over_odds": -300},    # no projection: skipped
]
PREDICTIONS = {"Jaylen Brown": {"player_id": 1, "mean": 26.0}}


def rows(version="ewma-v1", predictions=PREDICTIONS):
    return nba_alt.build_alt_rows(EVENT, LINES, predictions, "2026-11-04T17:00:00+00:00",
                                  "2026-11-04", model_version=version, dispersion=7.8)


def test_every_model_that_prices_lines_has_a_spread_for_the_ladder():
    from edgefinder.models import nba_context_points, nba_context_v2, nba_minutes_points, nba_points
    registered = {nba_points.MODEL_VERSION, nba_minutes_points.MODEL_VERSION,
                  nba_context_points.MODEL_VERSION, nba_context_v2.MODEL_VERSION}
    assert registered <= set(nba_alt.DISPERSIONS)
    table = nba_alt.ladder({version: 20.0 for version in registered}, rungs=[10, 20])
    assert len(table) == 2 and all(f"{v} chance %" in table.columns for v in registered)


def test_the_chance_of_at_least_a_total_falls_as_the_total_rises():
    chances = [nba_alt.p_at_least(k, 20.0, 7.8) for k in (10, 15, 20, 25, 30)]
    assert chances == sorted(chances, reverse=True)
    assert nba_alt.p_at_least(0, 20.0, 7.8) == pytest.approx(1.0)


def test_at_least_n_is_the_same_bet_as_over_n_minus_a_half():
    from edgefinder.betting import negbin
    assert nba_alt.p_at_least(15, 18.0, 7.8) == pytest.approx(
        float(negbin.over_prob(14.5, 18.0, 7.8)))


def test_fair_odds_are_the_break_even_price():
    assert nba_alt.fair_american(0.5) == -100
    assert nba_alt.fair_american(0.75) == -300
    assert nba_alt.fair_american(0.25) == 300
    assert nba_alt.fair_american(0.0) > 0 and nba_alt.fair_american(1.0) < 0   # clamped, finite


def test_the_ladder_has_a_chance_and_fair_odds_per_model_per_rung():
    table = nba_alt.ladder({"ewma-v1": 20.0, "minutes-v1": 26.0}, rungs=[10, 20, 30])
    assert list(table["Points"]) == ["10+", "20+", "30+"]
    assert table["minutes-v1 chance %"].iloc[1] > table["ewma-v1 chance %"].iloc[1]
    assert table["ewma-v1 chance %"].is_monotonic_decreasing


def test_only_half_point_lines_with_a_projection_are_priced():
    priced = rows()
    assert [r["threshold"] for r in priced] == [15, 25]
    assert {r["player"] for r in priced} == {"Jaylen Brown"}


def test_a_price_is_a_pick_when_the_blended_chance_beats_the_price():
    by_threshold = {r["threshold"]: r for r in rows()}
    # a 26-point projection makes 25+ likelier than +130 implies
    assert by_threshold[25]["is_pick"] and by_threshold[25]["pick_ev"] >= 0.02
    # 15+ at -1000 already prices in nearly all of it
    assert not by_threshold[15]["is_pick"] and by_threshold[15]["pick_ev"] is None


def test_a_long_shot_is_never_a_pick_however_good_the_price_looks():
    longshot = [{"player": "Jaylen Brown", "line": 44.5, "over_odds": 100000}]
    (row,) = nba_alt.build_alt_rows(
        EVENT, longshot, PREDICTIONS, "2026-11-04T17:00:00+00:00", "2026-11-04",
        model_version="ewma-v1", dispersion=7.8)
    assert row["model_p"] < nba_alt.MIN_MODEL_P
    assert not row["is_pick"] and row["pick_ev"] is None


def test_a_price_far_from_the_markets_is_excluded_as_a_data_problem():
    # model ~31% vs market 10.5% (+850): a 20-point gap, so not a pick
    far = [{"player": "Jaylen Brown", "line": 30.5, "over_odds": 850}]
    (row,) = nba_alt.build_alt_rows(
        EVENT, far, PREDICTIONS, "2026-11-04T17:00:00+00:00", "2026-11-04",
        model_version="ewma-v1", dispersion=7.8)
    assert row["model_p"] - row["market_p"] > nba_alt.MAX_DISAGREEMENT
    assert not row["is_pick"]


def test_appending_the_same_prices_twice_adds_nothing(tmp_path):
    path = tmp_path / "alt.csv"
    assert nba_alt.append_rows(rows(), path) == 2
    assert nba_alt.append_rows(rows(), path) == 0
    assert nba_alt.append_rows(rows("minutes-v1"), path) == 2   # another model is new


def test_one_failing_model_does_not_stop_the_others(tmp_path):
    from edgefinder.tracking.nba_recording import RegisteredModel

    def broken(event, names):
        raise RuntimeError("boom")

    models = [RegisteredModel("bad", 7.8, broken),
              RegisteredModel("good", 7.8, lambda event, names: PREDICTIONS)]
    added = nba_alt.record_event(EVENT, LINES, models, "2026-11-04T17:00:00+00:00",
                                 "2026-11-04", path=tmp_path / "alt.csv")
    assert added == {"bad": 0, "good": 2}


def settled(actual, today=dt.date(2026, 11, 6)):
    games = pd.DataFrame({"player_id": [1], "game_date": pd.to_datetime(["2026-11-04"]),
                          "pts": [actual]})
    return nba_alt.settle(pd.DataFrame(rows()), games, today)


def test_a_pick_wins_when_the_player_reaches_the_total():
    out = settled(25.0).set_index("threshold")
    assert out.loc[25, "result"] == "win"
    assert out.loc[25, "pnl_units"] == pytest.approx(1.30)
    assert pd.isna(out.loc[15, "result"])            # not a pick, so not graded


def test_a_pick_loses_one_unit_when_the_player_falls_short():
    out = settled(24.0).set_index("threshold")
    assert out.loc[25, "result"] == "loss" and out.loc[25, "pnl_units"] == -1.0


def test_a_player_who_never_played_is_voided_once_the_date_has_passed():
    others = pd.DataFrame({"player_id": [99], "game_date": pd.to_datetime(["2026-11-05"]),
                           "pts": [10.0]})
    out = nba_alt.settle(pd.DataFrame(rows()), others, dt.date(2026, 11, 6))
    assert (out["status"] == "void").all()


def test_the_summary_counts_only_graded_picks():
    summary = nba_alt.summary(settled(25.0))
    assert summary["picks"] == 1 and summary["settled"] == 1
    assert summary["record"] == "1-0" and summary["units"] == pytest.approx(1.30)


def test_suggestions_list_picks_best_first_and_merge_agreeing_models():
    ledger = pd.DataFrame(rows("ewma-v1") + rows("minutes-v1"))
    table = nba_alt.suggestions(ledger, "2026-11-04")
    assert list(table["Bet"]) == ["Jaylen Brown · 25+ points"]
    assert table.iloc[0]["Agree"] == 2


def test_suggestions_show_one_rung_per_player():
    lines = [{"player": "Jaylen Brown", "line": 24.5, "over_odds": 130},
             {"player": "Jaylen Brown", "line": 25.5, "over_odds": 150}]
    data = nba_alt.build_alt_rows(EVENT, lines, PREDICTIONS, "2026-11-04T17:00:00+00:00",
                                  "2026-11-04", model_version="ewma-v1", dispersion=7.8)
    assert sum(r["is_pick"] for r in data) == 2
    assert len(nba_alt.suggestions(pd.DataFrame(data), "2026-11-04")) == 1


def test_suggestions_with_no_picks_are_empty():
    assert nba_alt.suggestions(pd.DataFrame(rows()), "2030-01-01").empty


def test_games_recorded_counts_distinct_games_on_a_date():
    ledger = pd.DataFrame(rows("ewma-v1") + rows("minutes-v1"))
    assert nba_alt.games_recorded(ledger, "2026-11-04") == 1
    assert nba_alt.games_recorded(ledger, "2026-11-05") == 0


PAYLOAD = {"bookmakers": [{"key": "fanduel", "markets": [{
    "key": "player_points_alternate", "outcomes": [
        {"name": "Over", "description": "Jaylen Brown", "price": -250, "point": 14.5},
        {"name": "Over", "description": "Jaylen Brown", "price": 130, "point": 24.5},
        {"name": "Under", "description": "Jaylen Brown", "price": -150, "point": 24.5},
        {"name": "Over", "description": None, "price": 100, "point": 9.5},
    ]}]}]}


def test_alternate_lines_parse_to_over_only_rows():
    parsed = nba_props.parse_alt_lines(PAYLOAD)
    assert parsed == [
        {"player": "Jaylen Brown", "line": 14.5, "over_odds": -250},
        {"player": "Jaylen Brown", "line": 24.5, "over_odds": 130},
    ]


def test_a_payload_without_the_alternate_market_parses_to_nothing():
    assert nba_props.parse_alt_lines({"bookmakers": []}) == []
    other = {"bookmakers": [{"key": "fanduel", "markets": [{"key": "player_points", "outcomes": []}]}]}
    assert nba_props.parse_alt_lines(other) == []
