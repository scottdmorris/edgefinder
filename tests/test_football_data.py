from edgefinder.data import football_data as fd


def test_season_codes_midsummer():
    # July 2026: 2026-27 hasn't started, so train on the two most
    # recently completed seasons
    assert fd.season_codes(2026, 7) == ["2425", "2526"]


def test_season_codes_autumn():
    # October 2026: in the 2026-27 season
    assert fd.season_codes(2026, 10) == ["2526", "2627"]


def test_season_codes_spring():
    # March 2026: in the 2025-26 season
    assert fd.season_codes(2026, 3) == ["2425", "2526"]


def test_map_team_exact():
    known = {"Arsenal", "Chelsea"}
    assert fd.map_team_name("Arsenal", known) == "Arsenal"


def test_map_team_alias():
    known = {"Man United", "Man City"}
    assert fd.map_team_name("Manchester United", known) == "Man United"


def test_map_team_fuzzy():
    known = {"Nott'm Forest", "Everton"}
    assert fd.map_team_name("Everton FC", known) == "Everton"


def test_map_team_unknown_returns_none():
    assert fd.map_team_name("FC Nowhere", {"Arsenal"}) is None


def test_parse_csv_skips_bad_rows():
    text = (
        "Div,HomeTeam,AwayTeam,FTHG,FTAG\n"
        "E0,Arsenal,Chelsea,2,1\n"
        "E0,Spurs,,3,0\n"
        "E0,Leeds,Everton,x,1\n"
    )
    matches = fd._parse_csv(text)
    assert matches == [
        {"home": "Arsenal", "away": "Chelsea", "home_goals": 2, "away_goals": 1}
    ]
