import pandas as pd
import pytest

from edgefinder.tracking import nba_alt, nba_paper, nba_parlay

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Boston Celtics", "away": "Milwaukee Bucks"}
OTHER = {"event_id": "e2", "commence_time": "2026-11-05T00:30:00Z",
         "home": "New York Knicks", "away": "Chicago Bulls"}
LINES = [{"player": "Jaylen Brown", "line": 24.5, "over_odds": -110, "under_odds": -110}]
ALT = [{"player": "Jaylen Brown", "line": 24.5, "over_odds": 130}]
WHEN = "2026-11-04T17:00:00+00:00"


def ledger(version="minutes-v1", mean=27.0, event=EVENT, player="Jaylen Brown", pid=1):
    lines = [{**LINES[0], "player": player}]
    return pd.DataFrame(nba_paper.build_ledger_rows(
        event, lines, {player: {"player_id": pid, "mean": mean}}, WHEN, "2026-11-04",
        model_version=version, dispersion=7.8), columns=nba_paper.COLUMNS)


def alt(version="minutes-v1", mean=27.0, event=EVENT, player="Jaylen Brown", pid=1):
    lines = [{**ALT[0], "player": player}]
    return pd.DataFrame(nba_alt.build_alt_rows(
        event, lines, {player: {"player_id": pid, "mean": mean}}, WHEN, "2026-11-04",
        model_version=version, dispersion=7.8), columns=nba_alt.COLUMNS)


def candidates(main=None, extra=None):
    main = ledger() if main is None else main
    extra = alt() if extra is None else extra
    return nba_parlay.candidate_legs(main, extra, "2026-11-04", "minutes-v1")


def test_each_line_gives_an_over_and_an_under_leg_plus_its_x_plus_leg():
    table = candidates()
    assert set(table["Leg"]) == {"Jaylen Brown · Over 24.5 points",
                                 "Jaylen Brown · Under 24.5 points",
                                 "Jaylen Brown · 25+ points"}
    assert set(table["Stat"]) == {"Points"}


def test_over_and_under_probabilities_cover_the_whole_line():
    table = candidates().set_index("Leg")
    over = table.loc["Jaylen Brown · Over 24.5 points"]
    under = table.loc["Jaylen Brown · Under 24.5 points"]
    assert over["Model %"] + under["Model %"] == pytest.approx(100.0)
    assert over["prob"] + under["prob"] == pytest.approx(1.0)


def test_a_leg_is_priced_between_the_model_and_the_market():
    row = candidates().set_index("Leg").loc["Jaylen Brown · Over 24.5 points"]
    low, high = sorted([row["Model %"], row["Market %"]])
    assert low <= row["Blended %"] <= high
    assert row["Blended %"] == pytest.approx(0.3 * row["Model %"] + 0.7 * row["Market %"])


def test_only_the_chosen_model_and_date_are_used():
    both = pd.concat([ledger("ewma-v1", mean=15.0), ledger("minutes-v1", mean=27.0)])
    table = nba_parlay.candidate_legs(both, alt("minutes-v1"), "2026-11-04", "minutes-v1")
    assert (table.loc[table["Side"] == "Over", "Model %"] > 50).all()
    assert nba_parlay.candidate_legs(both, alt(), "2030-01-01", "minutes-v1").empty


def test_a_missing_x_plus_ledger_still_gives_over_under_legs():
    empty_alt = pd.DataFrame(columns=nba_alt.COLUMNS)
    assert len(nba_parlay.candidate_legs(ledger(), empty_alt, "2026-11-04", "minutes-v1")) == 2


def test_chosen_rows_become_builder_legs_with_their_teams():
    chosen = candidates().iloc[[0]]
    (leg,) = nba_parlay.to_legs(chosen, {1: "BOS"})
    assert leg.team == "BOS" and leg.event_id == "e1" and 0 < leg.prob < 1


def test_an_unknown_team_never_matches_another_unknown_player():
    both = pd.concat([candidates(), candidates(ledger(player="Other Guy", pid=2),
                                                alt(player="Other Guy", pid=2))])
    legs = nba_parlay.to_legs(both.drop_duplicates("player_id"), {})
    assert legs[0].team != legs[1].team


def test_every_bet_carries_its_line_and_team_abbreviations_for_live_tracking():
    table = candidates().set_index("Leg")
    over = table.loc["Jaylen Brown · Over 24.5 points"]
    x_plus = table.loc["Jaylen Brown · 25+ points"]
    assert over["line"] == 24.5 and x_plus["line"] == 24.5      # 25+ is the same bar as over 24.5
    assert (over["away_abbr"], over["home_abbr"]) == ("MIL", "BOS")


PLAYERS = {0: "brown", 1: "brown", 2: "embiid", 3: "maxey"}


def test_tapping_a_price_adds_it_and_tapping_again_removes_it():
    slip = nba_parlay.toggle_leg([], 0, PLAYERS)
    assert slip == [0]
    assert nba_parlay.toggle_leg(slip, 0, PLAYERS) == []


def test_a_second_price_for_the_same_player_replaces_the_first():
    assert nba_parlay.toggle_leg([0, 2], 1, PLAYERS) == [2, 1]      # brown's over -> brown's under


def test_prices_for_different_players_stack_up_in_the_order_added():
    assert nba_parlay.toggle_leg(nba_parlay.toggle_leg([0], 2, PLAYERS), 3, PLAYERS) == [0, 2, 3]


def test_toggling_never_changes_the_list_it_was_given():
    original = [0, 2]
    nba_parlay.toggle_leg(original, 1, PLAYERS)
    assert original == [0, 2]


def test_a_stake_turns_odds_into_dollars():
    result = nba_parlay.stake_outcomes(10.0, decimal_odds=4.0, ev_per_unit=0.07)
    assert result["total_return"] == pytest.approx(40.0)     # stake plus winnings
    assert result["profit_if_wins"] == pytest.approx(30.0)
    assert result["loss_if_misses"] == -10.0
    assert result["expected_profit"] == pytest.approx(0.70)


def test_a_zero_stake_is_fine_and_a_negative_one_is_rejected():
    assert nba_parlay.stake_outcomes(0.0, 4.0, 0.1)["total_return"] == 0.0
    with pytest.raises(ValueError):
        nba_parlay.stake_outcomes(-5.0, 4.0, 0.1)


def test_money_is_formatted_with_a_sign_only_when_asked():
    assert nba_parlay.money(12.5) == "$12.50"
    assert nba_parlay.money(12.5, signed=True) == "+$12.50"
    assert nba_parlay.money(-3.0, signed=True) == "-$3.00"
    assert nba_parlay.money(-3.0) == "-$3.00"
    assert nba_parlay.money(0.0, signed=True) == "$0.00"
    assert nba_parlay.money(1234.5) == "$1,234.50"


def test_a_chance_reads_as_one_in_n():
    assert nba_parlay.one_in(0.5) == "1 in 2"
    assert nba_parlay.one_in(0.027) == "1 in 37"
    assert nba_parlay.one_in(0.0001) == "1 in 10,000"
    assert nba_parlay.one_in(0.89) == "9 in 10"        # likely chances read as N in 10
    assert nba_parlay.one_in(1.0) == "10 in 10"
    assert nba_parlay.one_in(0.0) == "never"


def test_the_verdict_says_win_lose_or_even_in_plain_words():
    assert "wins about 12 cents" in nba_parlay.verdict(0.12)
    assert "loses about 30 cents" in nba_parlay.verdict(-0.30)
    assert "break-even" in nba_parlay.verdict(0.0)
    assert "break-even" in nba_parlay.verdict(-0.04)
    assert "hasn't been tested" in nba_parlay.verdict(0.12)    # a win is never claimed flat out


def test_headshots_come_from_the_nba_image_host_by_player_id():
    assert nba_parlay.headshot_url(1628369.0) == \
        "https://cdn.nba.com/headshots/nba/latest/260x190/1628369.png"


def test_models_have_plain_names_and_unknown_ones_pass_through():
    assert "minutes" in nba_parlay.model_name("minutes-v1")
    assert nba_parlay.model_name("some-future-model") == "some-future-model"


def test_player_teams_use_the_most_recent_game():
    games = pd.DataFrame({
        "player_id": [1, 1, 2], "team": ["MIL", "BOS", "CHI"],
        "game_date": pd.to_datetime(["2026-10-01", "2026-11-01", "2026-11-02"])})
    assert nba_parlay.player_teams(games) == {1: "BOS", 2: "CHI"}


def worthwhile_pool():
    """Two games, each with one player whose model sees real value."""
    first = ledger(mean=29.5)
    second = ledger(mean=29.5, event=OTHER, player="Other Guy", pid=2)
    return nba_parlay.candidate_legs(
        pd.concat([first, second]), pd.DataFrame(columns=nba_alt.COLUMNS),
        "2026-11-04", "minutes-v1")


def test_suggested_slips_use_at_most_one_leg_per_game():
    slips = nba_parlay.suggest_parlays(worthwhile_pool())
    assert not slips.empty
    assert (slips["Legs"] == 2).all()      # only two games have a leg worth betting
    for text in slips["Slip"]:
        games = [leg for leg in text.split("  +  ")]
        assert any("Jaylen Brown" in leg for leg in games)
        assert any("Other Guy" in leg for leg in games)


def test_a_slip_with_two_value_legs_has_the_joint_chance_of_both():
    slips = nba_parlay.suggest_parlays(worthwhile_pool())
    top = slips.iloc[0]
    assert top["Legs"] == 2
    assert 0 < top["Chance %"] < 100 and top["EV %"] > 0


def test_each_suggested_slip_says_which_bets_it_is_made_of():
    pool = worthwhile_pool()
    top = nba_parlay.suggest_parlays(pool).iloc[0]
    chosen = pool.loc[top["bets"]]
    assert len(chosen) == top["Legs"]
    assert set(chosen["Player"]) == {"Jaylen Brown", "Other Guy"}
    assert "  +  ".join(chosen["Leg"]) == top["Slip"]


def test_a_nearly_certain_leg_that_pays_almost_nothing_never_pads_a_slip():
    pool = worthwhile_pool().copy()
    padding = pool.iloc[0:1].assign(Leg="Padding Guy · 3+ points", Odds=-2000,
                                    **{"Leg EV %": 9.0})
    padding.index = [max(pool.index) + 1]
    with_padding = pd.concat([pool, padding])
    worthwhile = nba_parlay._worthwhile_legs(with_padding)
    assert "Padding Guy · 3+ points" not in set(worthwhile["Leg"])
    assert nba_parlay.MIN_LEG_DECIMAL > 1.0
    for slip in nba_parlay.suggest_parlays(with_padding, min_chance=0.0)["Slip"]:
        assert "Padding Guy" not in slip


def test_a_leg_that_pays_a_fair_amount_is_still_allowed():
    pool = worthwhile_pool()
    assert (pool["Odds"].map(nba_parlay.american_to_decimal) >= nba_parlay.MIN_LEG_DECIMAL).all()
    assert not nba_parlay._worthwhile_legs(pool).empty


def test_a_minimum_chance_drops_slips_that_are_too_unlikely():
    pool = worthwhile_pool()
    assert not nba_parlay.suggest_parlays(pool, min_chance=0.10).empty
    chance = nba_parlay.suggest_parlays(pool, min_chance=0.0)["Chance %"].iloc[0]
    assert nba_parlay.suggest_parlays(pool, min_chance=chance / 100 + 0.01).empty


def test_every_suggested_slip_clears_the_chance_it_was_asked_for():
    pool = worthwhile_pool()
    for floor in (0.05, 0.2, 0.3):
        slips = nba_parlay.suggest_parlays(pool, min_chance=floor)
        assert (slips["Chance %"] >= floor * 100.0 - 1e-9).all()


def test_the_styles_run_from_safer_to_bigger_payouts_and_balanced_is_the_default():
    assert nba_parlay.STYLES["Safer"] > nba_parlay.STYLES["Balanced"] > \
        nba_parlay.STYLES["Bigger payouts"] > 0
    assert nba_parlay.DEFAULT_STYLE == "Balanced"
    assert nba_parlay.suggest_parlays(worthwhile_pool()).equals(
        nba_parlay.suggest_parlays(worthwhile_pool(),
                                   min_chance=nba_parlay.STYLES["Balanced"]))


def test_a_slip_never_uses_two_legs_from_the_same_game():
    both_ways = pd.concat([
        ledger(mean=29.5),
        ledger(mean=29.5, event=OTHER, player="Other Guy", pid=2)])
    pool = nba_parlay.candidate_legs(both_ways, alt(mean=29.5), "2026-11-04", "minutes-v1")
    for bets in nba_parlay.suggest_parlays(pool, min_chance=0.0)["bets"]:
        chosen = pool.loc[bets]
        assert chosen["event_id"].is_unique


def test_with_value_in_only_one_game_there_is_nothing_to_combine():
    only_one = nba_parlay.candidate_legs(
        ledger(mean=29.5), pd.DataFrame(columns=nba_alt.COLUMNS), "2026-11-04", "minutes-v1")
    assert nba_parlay.suggest_parlays(only_one).empty


def test_a_safe_lock_that_is_worth_betting_may_join_a_slip():
    pool = worthwhile_pool().copy()
    lock = pool.iloc[0:1].assign(Leg="Safe Guy · 5+ points", Odds=-500, **{"Leg EV %": 3.0})
    lock.index = [max(pool.index) + 1]
    assert "Safe Guy · 5+ points" in set(nba_parlay._worthwhile_legs(pd.concat([pool, lock]))["Leg"])
    # -1000 is the cut-off in decimal terms: 1.10
    assert nba_parlay.american_to_decimal(-1000) == pytest.approx(nba_parlay.MIN_LEG_DECIMAL)


def _log(player_id, season, day, pts, reb=5, ast=3, fg3m=1):
    return {"player_id": player_id, "season": season, "game_date": pd.Timestamp(day),
            "pts": pts, "reb": reb, "ast": ast, "fg3m": fg3m}


def test_player_averages_are_the_season_mean_and_the_last_ten_mean():
    # 12 games in 2026-27 scoring 10, 11, ... 21: season mean 15.5, last ten = 12..21 -> 16.5
    rows = [_log(1, "2026-27", f"2026-11-{d:02d}", 9 + d) for d in range(1, 13)]
    rows.append(_log(1, "2025-26", "2026-04-01", 40))          # last season: not in the average
    averages = nba_parlay.player_averages(pd.DataFrame(rows))
    season, recent = averages[1]["pts"]
    assert season == pytest.approx(15.5) and recent == pytest.approx(16.5)


def test_a_player_with_no_games_this_season_uses_the_season_he_last_played():
    rows = [_log(1, "2026-27", "2026-11-01", 20), _log(2, "2025-26", "2026-04-01", 8),
            _log(2, "2025-26", "2026-04-03", 12)]
    averages = nba_parlay.player_averages(pd.DataFrame(rows))
    assert averages[2]["pts"] == (pytest.approx(10.0), pytest.approx(10.0))


def test_average_text_reads_simply_and_is_empty_for_unknown_players():
    averages = {7: {"pts": (21.44, 24.0), "reb": (6.0, 7.5)}}
    assert nba_parlay.average_text(averages, 7) == "avg 21.4 · last 10: 24.0"
    assert nba_parlay.average_text(averages, 7, "reb") == "avg 6.0 · last 10: 7.5"
    assert nba_parlay.average_text(averages, 99) == ""
