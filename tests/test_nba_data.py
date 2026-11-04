import datetime as dt
import os

import pandas as pd
import pytest

from edgefinder.data import nba_stats

TODAY = dt.date(2026, 11, 4)  # the 2026-27 season is in progress


def raw_frame():
    return pd.DataFrame({
        "PLAYER_ID": [1, 1, 2],
        "PLAYER_NAME": ["Ann Able", "Ann Able", "Bo Baker"],
        "TEAM_ID": [10, 10, 20],
        "TEAM_ABBREVIATION": ["AAA", "AAA", "BBB"],
        "GAME_ID": ["g2", "g1", "g1"],
        "GAME_DATE": ["2025-10-24", "2025-10-22", "2025-10-22"],
        "MATCHUP": ["AAA @ CCC", "AAA vs. BBB", "BBB @ AAA"],
        "WL": ["L", "W", "L"],
        "MIN": [30.5, 34.0, 28.0],
        "PTS": [18, 25, 12],
        "REB": [5, 7, 3],
        "AST": [4, 6, 2],
        "FG3M": [2, 3, 1],
        "STL": [1, 0, 1],
        "BLK": [0, 1, 0],
        "TOV": [2, 3, 1],
        "FGA": [15, 18, 10],
        "FTA": [4, 6, 2],
    })


class CountingFetcher:
    def __init__(self, frame=None, fail=False):
        self.frame = raw_frame() if frame is None else frame
        self.fail = fail
        self.calls = 0

    def __call__(self, season):
        self.calls += 1
        if self.fail:
            raise ConnectionError("stats.nba.com unreachable")
        return self.frame.copy()


def set_modified(path, when: dt.datetime):
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def test_season_labels():
    assert nba_stats.season_label(2025) == "2025-26"
    assert nba_stats.season_label(1999) == "1999-00"


def test_current_season_rolls_over_in_october():
    assert nba_stats.current_season(dt.date(2026, 11, 4)) == "2026-27"
    assert nba_stats.current_season(dt.date(2027, 3, 1)) == "2026-27"
    assert nba_stats.current_season(dt.date(2026, 9, 1)) == "2025-26"


def test_previous_season():
    assert nba_stats.previous_season("2026-27") == "2025-26"
    assert nba_stats.previous_season("2000-01") == "1999-00"


def test_normalize_standardizes_columns_and_sorts():
    games = nba_stats.normalize_player_games(raw_frame(), "2025-26")
    assert {"player_id", "game_date", "minutes", "pts", "is_home",
            "opponent", "season"} <= set(games.columns)
    assert pd.api.types.is_datetime64_any_dtype(games["game_date"])
    ann = games[games["player_id"] == 1]
    assert ann["game_date"].is_monotonic_increasing
    assert (games["season"] == "2025-26").all()


def test_normalize_derives_home_flag_and_opponent():
    games = nba_stats.normalize_player_games(raw_frame(), "2025-26")
    first = games[(games["player_id"] == 1)].iloc[0]
    second = games[(games["player_id"] == 1)].iloc[1]
    assert first["is_home"] and first["opponent"] == "BBB"
    assert not second["is_home"] and second["opponent"] == "CCC"


def test_completed_season_is_fetched_once_then_read_from_disk(tmp_path):
    fetcher = CountingFetcher()
    for _ in range(2):
        games = nba_stats.load_season(
            "2025-26", today=TODAY, fetcher=fetcher, directory=tmp_path)
    assert fetcher.calls == 1
    assert len(games) == 3


def test_current_season_refreshes_when_cache_is_stale(tmp_path):
    fetcher = CountingFetcher()
    nba_stats.load_season("2026-27", today=TODAY, fetcher=fetcher, directory=tmp_path)
    path = tmp_path / "games_2026-27.csv"
    set_modified(path, dt.datetime.now() - dt.timedelta(hours=24))
    nba_stats.load_season("2026-27", today=TODAY, fetcher=fetcher, directory=tmp_path)
    assert fetcher.calls == 2


def test_current_season_uses_fresh_cache(tmp_path):
    fetcher = CountingFetcher()
    for _ in range(3):
        nba_stats.load_season("2026-27", today=TODAY, fetcher=fetcher, directory=tmp_path)
    assert fetcher.calls == 1


def test_completed_season_cached_before_it_ended_is_refetched(tmp_path):
    fetcher = CountingFetcher()
    nba_stats.load_season("2025-26", today=TODAY, fetcher=fetcher, directory=tmp_path)
    # a copy saved in March would be missing the end of the season
    set_modified(tmp_path / "games_2025-26.csv", dt.datetime(2026, 3, 1))
    nba_stats.load_season("2025-26", today=TODAY, fetcher=fetcher, directory=tmp_path)
    assert fetcher.calls == 2


def test_stale_cache_is_returned_when_the_fetch_fails(tmp_path):
    good = CountingFetcher()
    nba_stats.load_season("2026-27", today=TODAY, fetcher=good, directory=tmp_path)
    set_modified(tmp_path / "games_2026-27.csv",
                 dt.datetime.now() - dt.timedelta(hours=24))
    broken = CountingFetcher(fail=True)
    games = nba_stats.load_season(
        "2026-27", today=TODAY, fetcher=broken, directory=tmp_path)
    assert broken.calls == 1
    assert len(games) == 3


def test_fetch_failure_without_any_cache_raises(tmp_path):
    with pytest.raises(nba_stats.NbaDataError):
        nba_stats.load_season("2026-27", today=TODAY,
                              fetcher=CountingFetcher(fail=True), directory=tmp_path)
