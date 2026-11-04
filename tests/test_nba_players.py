import pandas as pd

from edgefinder.data import nba_players


def test_names_are_normalized_across_accents_punctuation_and_suffixes():
    assert nba_players.normalize_name("Nikola Jokić") == "nikola jokic"
    assert nba_players.normalize_name("Jaren Jackson Jr.") == "jaren jackson"
    assert nba_players.normalize_name("P.J. Washington") == "pj washington"
    assert nba_players.normalize_name("Shai Gilgeous-Alexander") == "shai gilgeous alexander"
    assert nba_players.normalize_name("  Gary Trent  Jr ") == "gary trent"


def test_the_same_player_matches_across_feeds():
    assert nba_players.normalize_name("Luka Dončić") == nba_players.normalize_name("Luka Doncic")


def test_odds_team_names_map_to_nba_abbreviations():
    assert nba_players.team_abbreviation("Los Angeles Clippers") == "LAC"
    assert nba_players.team_abbreviation("Philadelphia 76ers") == "PHI"
    assert nba_players.team_abbreviation("Portland Trail Blazers") == "POR"
    assert nba_players.team_abbreviation("Detroit Pistons") == "DET"
    assert nba_players.team_abbreviation("Brooklyn Nets") == "BKN"
    assert nba_players.team_abbreviation("Charlotte Hornets") == "CHA"


def test_unknown_team_gives_none():
    assert nba_players.team_abbreviation("Seattle Supersonics") is None


def games():
    return pd.DataFrame({
        "player_id": [1, 1, 2, 3, 4],
        "player_name": ["Cade Cunningham", "Cade Cunningham", "Jaren Jackson Jr.",
                        "Nikola Jokić", "Traded Guy"],
        "team": ["DET", "DET", "MEM", "DEN", "OLD"],
        "game_date": pd.to_datetime(["2026-10-25", "2026-10-28", "2026-10-28",
                                     "2026-10-28", "2026-10-20"]),
    })


def test_players_are_matched_to_ids_within_the_two_teams_only():
    matched = nba_players.match_players(
        ["Cade Cunningham", "Jaren Jackson Jr.", "Nikola Jokic"], games(), {"DET", "MEM"})
    assert matched == {"Cade Cunningham": 1, "Jaren Jackson Jr.": 2}


def test_a_traded_player_uses_their_latest_team():
    frame = pd.concat([games(), pd.DataFrame({
        "player_id": [4], "player_name": ["Traded Guy"], "team": ["DET"],
        "game_date": pd.to_datetime(["2026-10-28"]),
    })], ignore_index=True)
    assert nba_players.match_players(["Traded Guy"], frame, {"DET"}) == {"Traded Guy": 4}
    assert nba_players.match_players(["Traded Guy"], frame, {"OLD"}) == {}


def test_unknown_names_are_left_out():
    assert nba_players.match_players(["Nobody Real"], games(), {"DET"}) == {}
