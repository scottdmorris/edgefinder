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


def test_with_value_in_only_one_game_there_is_nothing_to_combine():
    only_one = nba_parlay.candidate_legs(
        ledger(mean=29.5), pd.DataFrame(columns=nba_alt.COLUMNS), "2026-11-04", "minutes-v1")
    assert nba_parlay.suggest_parlays(only_one).empty
