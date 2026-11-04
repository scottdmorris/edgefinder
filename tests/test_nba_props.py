import pandas as pd

from edgefinder.data import nba_props

PAYLOAD = {
    "id": "91df8655",
    "commence_time": "2026-11-05T00:00:00Z",
    "home_team": "Detroit Pistons",
    "away_team": "Philadelphia 76ers",
    "bookmakers": [
        {"key": "fanduel", "markets": [{
            "key": "player_points",
            "last_update": "2026-11-04T05:27:23Z",
            "outcomes": [
                {"name": "Over", "description": "Duncan Robinson", "price": -130, "point": 13.5},
                {"name": "Under", "description": "Duncan Robinson", "price": -102, "point": 13.5},
                {"name": "Over", "description": "Javonte Green", "price": -132, "point": 5.5},
                {"name": "Under", "description": "Javonte Green", "price": 100, "point": 5.5},
                {"name": "Over", "description": "Cade Cunningham", "price": -130, "point": 23.5},
            ],
        }]},
        {"key": "otherbook", "markets": [{
            "key": "player_points",
            "outcomes": [
                {"name": "Over", "description": "Duncan Robinson", "price": -500, "point": 99.5},
            ],
        }]},
    ],
}


def by_player(rows):
    return {row["player"]: row for row in rows}


def test_over_and_under_are_paired_into_one_row_per_player_line():
    rows = by_player(nba_props.parse_player_lines(PAYLOAD))
    assert rows["Duncan Robinson"] == {
        "player": "Duncan Robinson", "line": 13.5,
        "over_odds": -130, "under_odds": -102,
    }
    assert rows["Javonte Green"]["under_odds"] == 100


def test_a_missing_side_is_kept_as_none():
    rows = by_player(nba_props.parse_player_lines(PAYLOAD))
    assert rows["Cade Cunningham"]["over_odds"] == -130
    assert rows["Cade Cunningham"]["under_odds"] is None


def test_only_fanduel_is_used():
    rows = nba_props.parse_player_lines(PAYLOAD)
    assert len(rows) == 3
    assert all(row["line"] != 99.5 for row in rows)


def test_payload_without_the_book_or_market_gives_no_rows():
    assert nba_props.parse_player_lines({"bookmakers": []}) == []
    other_market = {"bookmakers": [{"key": "fanduel", "markets": [{"key": "h2h", "outcomes": []}]}]}
    assert nba_props.parse_player_lines(other_market) == []


EVENT = {"event_id": "91df8655", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}


def test_snapshots_round_trip_through_the_csv(tmp_path):
    path = tmp_path / "props.csv"
    lines = nba_props.parse_player_lines(PAYLOAD)
    nba_props.append_snapshot(EVENT, "early", lines, "2026-11-04T16:00:00+00:00", path=path)
    nba_props.append_snapshot(EVENT, "late", lines[:1], "2026-11-04T22:30:00+00:00", path=path)
    loaded = nba_props.load_snapshots(path=path)
    assert len(loaded) == 4
    assert set(loaded["phase"]) == {"early", "late"}
    assert set(loaded["event_id"]) == {"91df8655"}


def test_early_snapshots_are_regrouped_into_events_and_lines():
    snapshots = pd.DataFrame([
        {"fetched_at": "t1", "phase": "early", "event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers", "player": "Cade Cunningham",
         "line": 23.5, "over_odds": -130.0, "under_odds": -102.0},
        {"fetched_at": "t1", "phase": "early", "event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers", "player": "Duncan Robinson",
         "line": 13.5, "over_odds": -130.0, "under_odds": float("nan")},
        {"fetched_at": "t2", "phase": "late", "event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers", "player": "Cade Cunningham",
         "line": 24.5, "over_odds": -120.0, "under_odds": 100.0},
        {"fetched_at": "t1", "phase": "early", "event_id": "e2", "commence_time": "2026-11-05T01:00:00Z",
         "home": "Boston Celtics", "away": "Milwaukee Bucks", "player": "Jayson Tatum",
         "line": 27.5, "over_odds": -110.0, "under_odds": -110.0},
    ])
    grouped = nba_props.early_snapshots_by_event(snapshots)
    assert [(event["event_id"], len(lines)) for event, lines in grouped] == [("e1", 2), ("e2", 1)]
    event, lines = grouped[0]
    assert event == {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
                     "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
    assert lines[0] == {"player": "Cade Cunningham", "line": 23.5,
                        "over_odds": -130, "under_odds": -102}   # the late 24.5 line is ignored
    assert lines[1]["under_odds"] is None


def test_loading_a_missing_file_gives_an_empty_frame(tmp_path):
    loaded = nba_props.load_snapshots(path=tmp_path / "nope.csv")
    assert loaded.empty
    assert "event_id" in loaded.columns
