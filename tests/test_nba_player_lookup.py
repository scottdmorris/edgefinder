import pandas as pd
import pytest

from edgefinder.tracking import nba_player_lookup as lookup


def log(player_id, name, team, date, pts, reb=5, ast=3, minutes=30.0, season="2025-26",
        home=True, opponent="MIL", wl="W"):
    return {"player_id": player_id, "player_name": name, "team": team,
            "game_date": pd.Timestamp(date), "pts": pts, "reb": reb, "ast": ast, "fg3m": 2,
            "stl": 1, "blk": 0, "minutes": minutes, "season": season, "is_home": home,
            "opponent": opponent, "wl": wl}


GAMES = pd.DataFrame([
    log(1, "Jaylen Brown", "BOS", "2025-11-01", 20, minutes=34),
    log(1, "Jaylen Brown", "PHI", "2025-11-03", 30, minutes=36),     # traded: latest team wins
    log(1, "Jaylen Brown", "PHI", "2025-11-05", 25, minutes=35, home=False, opponent="CHI"),
    log(2, "Jalen Brunson", "NYK", "2025-11-02", 28, minutes=38),
    log(3, "Luka Dončić", "LAL", "2025-11-02", 33, minutes=36),
    log(4, "Gary Trent Jr.", "TOR", "2025-11-02", 12, minutes=20),
])


def test_a_search_matches_every_word_ignoring_case_accents_and_suffixes():
    assert list(lookup.search(GAMES, "luka doncic")["player_name"]) == ["Luka Dončić"]
    assert list(lookup.search(GAMES, "GARY TRENT")["player_name"]) == ["Gary Trent Jr."]
    assert list(lookup.search(GAMES, "brown jaylen")["player_name"]) == ["Jaylen Brown"]


def test_a_partial_name_lists_every_match_most_played_first():
    found = lookup.search(GAMES, "ja")
    assert list(found["player_name"]) == ["Jaylen Brown", "Jalen Brunson"]


def test_a_player_is_listed_once_with_his_latest_team():
    found = lookup.search(GAMES, "jaylen")
    assert len(found) == 1 and found["team"].iloc[0] == "PHI"


def test_nothing_typed_or_nothing_found_gives_an_empty_result():
    assert lookup.search(GAMES, "").empty
    assert lookup.search(GAMES, "   ").empty
    assert lookup.search(GAMES, "zzzz").empty


def test_season_averages_are_per_game_means():
    brown = lookup.player_games(GAMES, 1)
    averages = lookup.season_averages(brown)
    assert averages["games"] == 3
    assert averages["pts"] == pytest.approx(25.0)
    assert averages["minutes"] == pytest.approx(35.0)
    assert lookup.season_averages(brown.iloc[0:0]) == {"games": 0}


def test_a_young_season_falls_back_to_last_season():
    history = pd.DataFrame([log(1, "A", "X", "2025-04-01", 20, season="2024-25"),
                            log(1, "A", "X", "2025-04-03", 22, season="2024-25"),
                            log(1, "A", "X", "2025-10-30", 10, season="2025-26")])
    assert set(lookup.current_season_games(history)["season"]) == {"2024-25"}


def test_an_established_season_is_used_as_is():
    history = pd.DataFrame([log(1, "A", "X", f"2025-11-0{d}", 20, season="2025-26")
                            for d in range(1, 5)]
                           + [log(1, "A", "X", "2025-04-01", 99, season="2024-25")])
    assert set(lookup.current_season_games(history)["season"]) == {"2025-26"}


def test_recent_games_are_newest_first_with_home_and_away_marked():
    shown = lookup.recent_games(lookup.player_games(GAMES, 1), count=2)
    assert list(shown["Pts"]) == [25, 30]
    assert shown["Opponent"].iloc[0] == "@ CHI" and shown["Opponent"].iloc[1] == "vs MIL"
    assert list(shown.columns) == ["Date", "Opponent", "Result", "Min", "Pts", "Reb", "Ast", "3PM"]


def test_the_hit_rate_counts_games_over_and_under_a_line():
    brown = lookup.player_games(GAMES, 1)          # 20, 30, 25
    rate = lookup.hit_rate(brown, "pts", 24.5)
    assert (rate["games"], rate["over"], rate["under"]) == (3, 2, 1)
    assert rate["over_pct"] == pytest.approx(200 / 3)


def test_landing_exactly_on_a_whole_number_line_is_neither_over_nor_under():
    rate = lookup.hit_rate(lookup.player_games(GAMES, 1), "pts", 25)
    assert (rate["over"], rate["under"]) == (1, 1)


def test_the_hit_rate_can_look_at_only_the_last_few_games():
    rate = lookup.hit_rate(lookup.player_games(GAMES, 1), "pts", 24.5, last=2)   # 30, 25
    assert (rate["games"], rate["over"]) == (2, 2)


def test_a_player_with_no_games_has_a_zero_hit_rate_not_a_crash():
    empty = lookup.player_games(GAMES, 999)
    assert lookup.hit_rate(empty, "pts", 20.5) == {"games": 0, "over": 0, "under": 0,
                                                    "over_pct": 0.0}
