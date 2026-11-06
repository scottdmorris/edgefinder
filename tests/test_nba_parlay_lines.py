"""Which line to feature when a player has several, and where each stat's averages live."""

import pandas as pd

from edgefinder.tracking import nba_parlay


def lines_for(*pairs):
    """Over legs from (line, over odds) pairs, plus an unrelated under."""
    return pd.DataFrame([{"Side": "Over", "line": line, "Odds": odds} for line, odds in pairs]
                        + [{"Side": "Under", "line": 99.5, "Odds": -110}])


def test_the_featured_line_is_the_one_closest_to_a_coin_flip():
    # implied chances: -250 -> 71.4%, +100 -> 50.0%, +300 -> 25.0%; +100 is the coin flip
    assert nba_parlay.main_line(lines_for((7.5, -250), (9.5, 100), (11.5, 300))) == 9.5


def test_a_tie_between_two_lines_takes_the_lower_one():
    # -110 -> 52.4% and +110 -> 47.6%: both 2.4 points from even
    assert nba_parlay.main_line(lines_for((12.5, 110), (11.5, -110))) == 11.5


def test_a_single_line_is_featured_and_a_player_with_no_over_has_none():
    assert nba_parlay.main_line(lines_for((24.5, -110))) == 24.5
    only_under = pd.DataFrame([{"Side": "Under", "line": 5.5, "Odds": -110}])
    assert nba_parlay.main_line(only_under) is None


def test_each_stat_reads_its_averages_from_the_matching_game_log_column():
    assert [nba_parlay.stat_column(s) for s in ("points", "rebounds", "assists", "threes")] == [
        "pts", "reb", "ast", "fg3m"]


# ---- the Kalshi-style ladder -------------------------------------------------------------------------------------

def leg(index, side, line, odds, market, model):
    return pd.Series({"Side": side, "line": line, "Odds": odds, "Market %": market,
                      "Model %": model}, name=index)


def player(*legs):
    return pd.DataFrame(list(legs))


def test_a_price_is_shown_in_cents_like_kalshi():
    assert [nba_parlay.cents(o) for o in (100, -300, 300, -1000, 900)] == [50, 75, 25, 91, 10]


def test_over_under_lines_become_at_least_steps_in_order_with_both_sides():
    rows = player(
        leg(10, "Over", 19.5, -250, 70.0, 75.0), leg(11, "Under", 19.5, 200, 30.0, 25.0),
        leg(12, "Over", 9.5, -1000, 90.0, 92.0), leg(13, "Under", 9.5, 600, 10.0, 8.0))
    steps = nba_parlay.ladder(rows)
    assert [s["threshold"] for s in steps] == [10, 20]            # over 9.5 = 10+, over 19.5 = 20+
    twenty = steps[1]
    assert (twenty["yes"], twenty["no"]) == (10, 11)
    assert twenty["market"] == 70.0 and twenty["model"] == 75.0


def test_x_plus_legs_add_steps_with_only_a_yes_side():
    rows = player(leg(1, "Over", 24.5, -110, 52.0, 55.0), leg(2, "Under", 24.5, -110, 48.0, 45.0),
                  leg(3, "30+", 29.5, 300, 24.0, 22.0), leg(4, "35+", 34.5, 900, 9.0, 8.0))
    steps = nba_parlay.ladder(rows)
    assert [s["threshold"] for s in steps] == [25, 30, 35]
    assert steps[0]["no"] == 2 and steps[1]["no"] is None and steps[2]["no"] is None


def test_when_a_threshold_has_an_over_under_and_an_x_plus_the_two_sided_one_wins():
    rows = player(leg(1, "Over", 24.5, -110, 52.0, 55.0), leg(2, "Under", 24.5, -110, 48.0, 45.0),
                  leg(3, "25+", 24.5, -105, 51.0, 54.0))
    [step] = nba_parlay.ladder(rows)
    assert step["yes"] == 1 and step["no"] == 2


def test_a_player_with_only_unders_or_nothing_has_no_steps():
    assert nba_parlay.ladder(player(leg(1, "Under", 5.5, -110, 48.0, 45.0))) == []


def test_the_first_step_shown_is_the_one_closest_to_a_coin_flip_lower_on_a_tie():
    steps = [{"threshold": 10, "market": 90.0}, {"threshold": 20, "market": 55.0},
             {"threshold": 25, "market": 45.0}, {"threshold": 30, "market": 20.0}]
    assert nba_parlay.default_step(steps)["threshold"] == 20     # 55 and 45 are both 5 away


# ---- one table across every stat -----------------------------------------------------------------------------------------

FOUND = {"kalshi": {"rebounds": ["ewma-v1"], "points": ["ewma-v1", "minutes-v1"],
                    "threes": ["ewma-v1"]},
         "fanduel": {"points": ["ewma-v1", "minutes-v1"]}}


def test_sources_are_listed_fanduel_first_and_each_sources_models_are_merged():
    assert nba_parlay.books_on(FOUND) == ["fanduel", "kalshi"]
    assert nba_parlay.books_on({"kalshi": {}, "fanduel": {}, "zzz": {}}) == [
        "fanduel", "kalshi", "zzz"]
    assert nba_parlay.model_versions(FOUND, "kalshi") == ["minutes-v1", "ewma-v1"]
    assert nba_parlay.model_versions(FOUND, "fanduel") == ["minutes-v1", "ewma-v1"]


def test_a_stat_the_chosen_model_did_not_price_falls_back_to_the_baseline():
    assert nba_parlay.version_for(["ewma-v1", "minutes-v1"], "minutes-v1") == "minutes-v1"
    assert nba_parlay.version_for(["ewma-v1"], "minutes-v1") == "ewma-v1"
    assert nba_parlay.version_for(["context-v1", "minutes-v1"], "ewma-v1") == "context-v1"


# ---- bench players' locks are not suggested ------------------------------------------------------------

def test_bench_players_are_the_ones_averaging_under_18_minutes_lately():
    averages = {1: {"minutes": (30.0, 17.9)}, 2: {"minutes": (12.0, 18.0)}, 3: {"pts": (5.0, 5.0)}}
    assert nba_parlay.bench_players(averages) == frozenset({1})    # 18.0 exactly is not bench


def test_minutes_join_the_averages_when_the_game_logs_have_them():
    games = pd.DataFrame({"player_id": [1, 1], "season": ["2026-27"] * 2,
                          "game_date": pd.to_datetime(["2026-11-01", "2026-11-03"]),
                          "pts": [10, 20], "reb": [1, 3], "ast": [0, 2], "fg3m": [0, 1],
                          "minutes": [12.0, 16.0]})
    assert nba_parlay.player_averages(games)[1]["minutes"] == (14.0, 14.0)
