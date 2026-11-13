"""The "known out" definition of an absence, which matches what the injury report gives live:
a player counts as missing only if he had already missed the team's previous game, is still
with the team, and played for it this season."""

import pytest

from edgefinder.models import nba_context
from test_nba_context import FULL, OPP, WITHOUT_P2, box, frame, lost

DAYS = ["2025-11-01", "2025-11-03", "2025-11-05", "2025-11-07"]


def season_of(*sides, opponent=OPP):
    """AAA plays BBB once per entry in `sides`; each entry is AAA's box score."""
    boxes = []
    for n, (day, players) in enumerate(zip(DAYS, sides), start=1):
        boxes += [box(f"g{n}", day, "AAA", "BBB", players), box(f"g{n}", day, "BBB", "AAA", opponent)]
    return frame(*boxes)


def known(games):
    return nba_context.absence_table(games, known_only=True)


def test_the_first_game_a_player_misses_is_not_yet_known():
    games = season_of(FULL, WITHOUT_P2, WITHOUT_P2)
    assert lost(known(games), "AAA", "g2")["n_absent"] == 0.0
    assert lost(nba_context.absence_table(games), "AAA", "g2")["n_absent"] == 1.0   # the old rule


def test_the_second_game_in_a_row_he_misses_counts():
    row = lost(known(season_of(FULL, WITHOUT_P2, WITHOUT_P2)), "AAA", "g3")
    assert row["n_absent"] == 1.0 and row["lost_min"] == pytest.approx(30.0)


def test_a_player_who_has_moved_to_another_team_is_not_missing_from_his_old_one():
    moved = OPP + [(2, 30.0, 18.0)]                      # p2 now plays for BBB
    games = frame(
        box("g1", DAYS[0], "AAA", "BBB", FULL), box("g1", DAYS[0], "BBB", "AAA", OPP),
        box("g2", DAYS[1], "AAA", "BBB", WITHOUT_P2), box("g2", DAYS[1], "BBB", "AAA", OPP),
        box("g3", DAYS[2], "AAA", "BBB", WITHOUT_P2), box("g3", DAYS[2], "BBB", "AAA", moved))
    assert lost(known(games), "AAA", "g3")["n_absent"] == 0.0


def test_last_seasons_roster_does_not_carry_into_a_new_season():
    games = frame(
        box("g1", "2025-04-01", "AAA", "BBB", FULL, season="2024-25"),
        box("g1", "2025-04-01", "BBB", "AAA", OPP, season="2024-25"),
        box("g2", "2025-04-03", "AAA", "BBB", WITHOUT_P2, season="2024-25"),
        box("g2", "2025-04-03", "BBB", "AAA", OPP, season="2024-25"),
        box("g3", "2025-10-22", "AAA", "BBB", WITHOUT_P2), box("g3", "2025-10-22", "BBB", "AAA", OPP),
        box("g4", "2025-10-24", "AAA", "BBB", WITHOUT_P2), box("g4", "2025-10-24", "BBB", "AAA", OPP))
    table = known(games)
    assert lost(table, "AAA", "g3")["n_absent"] == 0.0
    assert lost(table, "AAA", "g4")["n_absent"] == 0.0   # he has not played for AAA this season


def test_adding_context_can_use_the_known_definition():
    games = season_of(FULL, WITHOUT_P2, WITHOUT_P2)
    out = nba_context.add_context(games, games, known_only=True)
    assert len(out) == len(games)
    assert set(out.loc[out["game_id"] == "g2", "n_absent"]) == {0.0}


# ---- live ------------------------------------------------------------------------------------

def test_live_a_player_listed_out_counts_when_he_is_on_this_seasons_roster():
    slate = nba_context.SlateContext(season_of(FULL, FULL), "2025-11-06", known_only=True)
    assert slate.team("AAA", "BBB", {2})["n_absent"] == 1.0


def test_live_a_player_whose_latest_game_was_for_another_team_is_ignored():
    moved = OPP + [(2, 30.0, 18.0)]
    games = frame(
        box("g1", DAYS[0], "AAA", "BBB", FULL), box("g1", DAYS[0], "BBB", "AAA", OPP),
        box("g2", DAYS[1], "AAA", "BBB", WITHOUT_P2), box("g2", DAYS[1], "BBB", "AAA", moved))
    slate = nba_context.SlateContext(games, "2025-11-06", known_only=True)
    assert slate.team("AAA", "BBB", {2})["n_absent"] == 0.0
    assert slate.team("BBB", "AAA", {2})["n_absent"] == 1.0
    assert nba_context.SlateContext(games, "2025-11-06").team("AAA", "BBB", {2})["n_absent"] == 1.0


def test_live_last_seasons_roster_is_ignored():
    games = frame(
        box("g1", "2025-04-01", "AAA", "BBB", FULL, season="2024-25"),
        box("g1", "2025-04-01", "BBB", "AAA", OPP, season="2024-25"),
        box("g2", "2025-10-22", "AAA", "BBB", WITHOUT_P2), box("g2", "2025-10-22", "BBB", "AAA", OPP))
    slate = nba_context.SlateContext(games, "2025-10-24", known_only=True)
    assert slate.team("AAA", "BBB", {2})["n_absent"] == 0.0
