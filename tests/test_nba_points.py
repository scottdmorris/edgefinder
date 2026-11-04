import pandas as pd
import pytest

from edgefinder.models import nba_points

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}


def games():
    dates = pd.to_datetime(["2026-10-25", "2026-10-27", "2026-10-29"])
    frames = []
    for player_id, name, team, points in [
        (1, "Cade Cunningham", "DET", [20, 24, 28]),
        (2, "Joel Embiid", "PHI", [30, 30, 30]),
        (3, "Somebody Else", "BOS", [40, 40, 40]),
    ]:
        frames.append(pd.DataFrame({
            "player_id": player_id, "player_name": name, "team": team,
            "season": "2026-27", "game_date": dates, "minutes": 30.0, "pts": points,
        }))
    return pd.concat(frames, ignore_index=True)


def project(names):
    return nba_points.project_event(EVENT, names, games(),
                                    season="2026-27", game_date="2026-11-04")


def test_only_players_on_the_two_teams_are_projected():
    projections = project(["Cade Cunningham", "Joel Embiid", "Somebody Else"])
    assert set(projections) == {"Cade Cunningham", "Joel Embiid"}


def test_a_flat_scoring_history_projects_to_that_level():
    assert project(["Joel Embiid"])["Joel Embiid"]["mean"] == pytest.approx(30.0)


def test_recent_games_count_more_than_old_ones():
    mean = project(["Cade Cunningham"])["Cade Cunningham"]["mean"]
    assert 24.0 < mean < 28.0  # above the plain average of 24, below the latest 28


def test_projection_carries_the_player_id():
    assert project(["Cade Cunningham"])["Cade Cunningham"]["player_id"] == 1


def test_unknown_players_get_no_projection():
    assert project(["Nobody Real"]) == {}
