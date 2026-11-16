"""The team side of the Players screen: a team's record, how it scores and defends against the
league, who plays, and how teammates' numbers change when a regular sits."""

import pandas as pd
import pytest

from edgefinder.api import teams

SEASON = "2026-27"


def side(game_id, day, team, opponent, home, won, players):
    """One team's box score. `players` is [(player_id, minutes, pts)]; every player shoots
    the same, so possessions follow the points."""
    return [{"player_id": pid, "player_name": f"P{pid}", "team": team, "opponent": opponent,
             "game_id": game_id, "game_date": pd.Timestamp(day), "season": SEASON,
             "is_home": home, "wl": "W" if won else "L", "minutes": minutes, "pts": pts,
             "reb": 5, "ast": 3, "fg3m": 1, "fga": pts / 2, "fta": 0, "tov": 0}
            for pid, minutes, pts in players]


def game(game_id, day, home, away, home_won, home_players, away_players):
    return side(game_id, day, home, away, True, home_won, home_players) + \
        side(game_id, day, away, home, False, not home_won, away_players)


BOS_FULL = [(1, 36, 30), (2, 34, 20), (3, 20, 10)]
BOS_NO_1 = [(2, 38, 28), (3, 30, 16)]                 # player 1 sits: the others score more
MIL = [(10, 36, 25), (11, 30, 15)]
NYK = [(20, 36, 20), (21, 30, 10)]

GAMES = pd.DataFrame(
    game("g1", "2026-11-01", "BOS", "MIL", True, BOS_FULL, MIL)
    + game("g2", "2026-11-03", "MIL", "BOS", True, MIL, BOS_FULL)
    + game("g3", "2026-11-05", "BOS", "NYK", True, BOS_NO_1, NYK)
    + game("g4", "2026-11-07", "NYK", "BOS", False, NYK, BOS_NO_1)
    + game("g5", "2026-11-09", "MIL", "NYK", True, MIL, NYK))


def test_the_search_list_has_every_team_that_played_with_its_full_name():
    found = {t["code"]: t for t in teams.team_options(GAMES)}
    assert set(found) == {"BOS", "MIL", "NYK"}
    assert found["BOS"]["name"] == "Boston Celtics" and found["BOS"]["plain"] == "boston celtics"
    assert found["BOS"]["logo"].endswith("logo.svg")


def test_the_record_counts_wins_home_and_away_and_the_current_streak():
    record = teams.record(teams.team_games(GAMES), "BOS")
    assert (record["wins"], record["losses"]) == (3, 1)
    assert record["home"] == "2-0" and record["away"] == "1-1"
    assert record["streak"] == "W2" and record["last10"] == "3-1"


def test_ratings_are_per_100_possessions_and_ranked_best_first():
    table = teams.ratings(teams.team_games(GAMES))
    bos = table.loc["BOS"]
    assert bos["ppg"] == pytest.approx((60 + 60 + 44 + 44) / 4)
    assert bos["ortg"] == pytest.approx(200.0)           # 2 points a possession in this toy data
    assert bos["ortg_rank"] in (1, 2, 3) and table["drtg_rank"].min() == 1
    assert table.loc[table["net"].idxmax(), "net_rank"] == 1


def test_recent_results_are_newest_first_with_the_score():
    first = teams.results(teams.team_games(GAMES), "BOS")[0]
    assert first == {"date": "2026-11-07", "opponent": "NYK", "home": False, "result": "W",
                     "score": "44-30"}


def test_the_roster_is_who_last_played_for_the_team_with_per_game_averages():
    roster = {p["id"]: p for p in teams.roster(GAMES, "BOS")}
    assert set(roster) == {1, 2, 3}
    assert roster[1]["games"] == 2 and roster[1]["pts"] == pytest.approx(30.0)
    assert roster[2]["games"] == 4 and roster[2]["pts"] == pytest.approx(24.0)
    assert list(roster)[0] == 2                          # most minutes first


def test_teammates_numbers_with_and_without_a_player_who_sits():
    split = teams.with_without(GAMES, "BOS", 1)
    by_id = {row["id"]: row for row in split["teammates"]}
    assert (split["with_games"], split["without_games"]) == (2, 2)
    assert by_id[3]["pts_with"] == pytest.approx(10.0) and by_id[3]["pts_without"] == pytest.approx(16.0)
    assert by_id[3]["min_with"] == pytest.approx(20.0) and by_id[3]["min_without"] == pytest.approx(30.0)
    assert split["teammates"][0]["id"] == 2              # the biggest change in points first


def test_without_enough_games_on_both_sides_there_is_no_split():
    assert teams.with_without(GAMES, "BOS", 2)["teammates"] == []     # he never sat


# ---- the routes ---------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from edgefinder.api import app as api_app, service
    from edgefinder.data import nba_injuries

    service.clear_cache()
    monkeypatch.setattr(service, "load_games", lambda: GAMES)
    monkeypatch.setattr(service, "load_ledger", lambda: pd.DataFrame(columns=teams.nba_paper.COLUMNS))
    monkeypatch.setattr(teams, "_season_games", lambda: GAMES)
    injured = [nba_injuries.Injury("P1", "BOS", "Out", "knee")]
    monkeypatch.setattr(nba_injuries, "fetch_injuries", lambda: injured)
    yield TestClient(api_app.app)
    service.clear_cache()


def test_the_team_list_and_a_team_page_are_served(client):
    assert {t["code"] for t in client.get("/api/teams").json()} == {"BOS", "MIL", "NYK"}
    page = client.get("/api/teams/bos").json()
    assert page["code"] == "BOS" and page["record"]["wins"] == 3
    assert page["ratings"]["net_rank"] >= 1 and len(page["results"]) == 4
    assert page["injuries"] == [{"name": "P1", "status": "OUT", "detail": "knee"}]
    [sitting] = page["absences"]                     # a regular who is out, and the split
    assert sitting["id"] == 1 and sitting["without_games"] == 2


def test_an_unknown_or_malformed_team_is_a_404(client):
    assert client.get("/api/teams/ZZZ").status_code == 404
    assert client.get("/api/teams/..%2F..").status_code == 404


def test_a_missing_injury_report_still_serves_the_page(client, monkeypatch):
    from edgefinder.api import service
    from edgefinder.data import nba_injuries

    def down():
        raise nba_injuries.InjuryDataError("down")

    service.clear_cache()
    monkeypatch.setattr(nba_injuries, "fetch_injuries", down)
    page = client.get("/api/teams/BOS").json()
    assert page["injury_report"] is False and page["absences"] == []
