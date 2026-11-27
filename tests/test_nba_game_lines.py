from edgefinder.data import nba_game_lines

EVENT = {"event_id": "nba1", "commence_time": "2026-11-28T00:00:00Z",
         "away": "Boston Celtics", "home": "Denver Nuggets"}


def market(key, first, second, **fields):
    sides = ("home", "away") if key == "spreads" else (None, None)
    return {"key": key, "line_type": "main", "outcomes": [
        {"name": name, "side": side, "point": point}
        for name, side, point in zip(("Over", "Under"), sides, (first, second))
    ], **fields}


GAME = {"away_team": EVENT["away"], "home_team": EVENT["home"],
        "commence_time": EVENT["commence_time"], "bookmakers": [{"key": "draftkings", "markets": [
            market("totals", 110.5, 110.5, team=EVENT["home"]),
            market("totals", 57.5, 57.5, period="q1"),
            market("totals", 221.5, 221.5),
            market("spreads", -3, 3, period="1h"),
            market("spreads", -6, 6),
        ]}]}


def test_archive_keeps_the_full_game_quote_and_rejects_post_tip_rows(tmp_path):
    path = tmp_path / "game-lines.csv"
    tasks = [(EVENT, "late")]
    before = "2026-11-27T23:30:00Z"
    assert nba_game_lines.archive([GAME], tasks, before, path) == 1
    assert nba_game_lines.archive([GAME], tasks, EVENT["commence_time"], path) == 0
    assert nba_game_lines.latest(nba_game_lines.load(path), "fanduel", ["nba1"]) == {
        "book": "draftkings", "home_spread": -6, "total": 221.5, "as_of": before,
    }


def test_unpaired_spread_or_total_is_skipped():
    game = GAME | {"bookmakers": [{"key": "fanduel", "markets": [
        market("spreads", -3, 4),
        market("totals", 220, 221),
    ]}]}
    assert nba_game_lines.parse(game) == []
