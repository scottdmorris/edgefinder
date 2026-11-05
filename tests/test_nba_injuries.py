import pandas as pd
import pytest

from edgefinder.data import nba_injuries

PAYLOAD = {"injuries": [
    {"displayName": "New York Knicks", "id": "18", "injuries": [
        {"athlete": {"displayName": "Mitchell Robinson"}, "status": "Out",
         "shortComment": "Ankle."},
        {"athlete": {"displayName": "Josh Hart"}, "status": "Day-To-Day", "shortComment": ""},
        {"athlete": {"displayName": "Doubtful Dan"}, "status": "Doubtful"},
        {"athlete": {}, "status": "Out"},                     # no name: skipped
    ]},
    {"displayName": "Boston Celtics", "id": "2", "injuries": [
        {"athlete": {"displayName": "Jayson Tatum"}, "status": "Questionable"}]},
    {"displayName": "Somewhere Mystery", "id": "99", "injuries": [
        {"athlete": {"displayName": "Lost Player"}, "status": "Out"}]},
]}


def by_name(injuries):
    return {i.name: i for i in injuries}


def test_every_named_injury_is_parsed_with_team_status_and_comment():
    injuries = by_name(nba_injuries.parse_injuries(PAYLOAD))
    assert set(injuries) == {"Mitchell Robinson", "Josh Hart", "Doubtful Dan", "Jayson Tatum",
                             "Lost Player"}
    robinson = injuries["Mitchell Robinson"]
    assert (robinson.team, robinson.status, robinson.detail) == ("NYK", "Out", "Ankle.")
    assert injuries["Jayson Tatum"].team == "BOS"


def test_only_out_and_doubtful_count_as_not_playing():
    injuries = by_name(nba_injuries.parse_injuries(PAYLOAD))
    assert injuries["Mitchell Robinson"].is_out and injuries["Doubtful Dan"].is_out
    assert not injuries["Josh Hart"].is_out and not injuries["Jayson Tatum"].is_out


def test_a_badge_says_out_for_anyone_ruled_out_and_the_feeds_word_otherwise():
    injuries = by_name(nba_injuries.parse_injuries(PAYLOAD))
    assert nba_injuries.label(injuries["Mitchell Robinson"]) == "OUT"
    assert nba_injuries.label(injuries["Doubtful Dan"]) == "OUT"
    assert nba_injuries.label(injuries["Josh Hart"]) == "DAY-TO-DAY"
    assert nba_injuries.label(injuries["Jayson Tatum"]) == "QUESTIONABLE"


def test_a_team_name_that_is_not_recognised_gets_no_tricode_instead_of_failing():
    assert by_name(nba_injuries.parse_injuries(PAYLOAD))["Lost Player"].team == ""


def test_an_empty_or_odd_payload_is_no_injuries():
    assert nba_injuries.parse_injuries({}) == []
    assert nba_injuries.parse_injuries({"injuries": [{"displayName": "New York Knicks"}]}) == []


def test_a_listed_player_can_be_looked_up_by_name_ignoring_accents_and_case():
    lookup = nba_injuries.status_by_name(nba_injuries.parse_injuries(PAYLOAD))
    assert lookup["mitchell robinson"].status == "Out"


def test_only_players_ruled_out_on_a_matched_roster_become_ids():
    games = pd.DataFrame({
        "player_id": [1, 2, 3], "player_name": ["Mitchell Robinson", "Josh Hart", "Doubtful Dan"],
        "team": ["NYK", "NYK", "NYK"], "season": ["2025-26"] * 3,
        "game_date": pd.to_datetime(["2025-11-01"] * 3)})
    ids = nba_injuries.out_player_ids(nba_injuries.parse_injuries(PAYLOAD), games, "2025-26")
    assert ids == {1, 3}              # Out and Doubtful; Josh Hart is only day-to-day


def test_an_unmatched_player_is_left_out_not_guessed():
    games = pd.DataFrame({
        "player_id": [9], "player_name": ["Somebody Else"], "team": ["NYK"],
        "season": ["2025-26"], "game_date": pd.to_datetime(["2025-11-01"])})
    assert nba_injuries.out_player_ids(nba_injuries.parse_injuries(PAYLOAD), games,
                                       "2025-26") == set()


def test_a_failed_fetch_becomes_one_clear_error_without_leaking_details(monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionError("secret details")

    monkeypatch.setattr(nba_injuries.requests, "get", boom)
    with pytest.raises(nba_injuries.InjuryDataError) as error:
        nba_injuries.fetch_injuries()
    assert "ConnectionError" in str(error.value) and "secret" not in str(error.value)
