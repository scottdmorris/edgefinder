"""NBA player game logs from the free nba_api package (stats.nba.com).

One league-wide call returns every player-game of a season, so a whole
training set is a handful of requests. A completed season never changes
and is cached for good; the current season refreshes every few hours.
"""

import datetime as dt
import logging
import re
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

NBA_DIR = Path(__file__).resolve().parents[3] / "data" / "nba"
CURRENT_SEASON_MAX_AGE_SECONDS = 6 * 3600
REQUEST_TIMEOUT_SECONDS = 40
SEASON_STARTS_IN_MONTH = 10  # October
SEASON_ENDS = (7, 1)         # anything cached before July 1 may be partial

COLUMN_MAP = {
    "PLAYER_ID": "player_id", "PLAYER_NAME": "player_name",
    "TEAM_ID": "team_id", "TEAM_ABBREVIATION": "team",
    "GAME_ID": "game_id", "GAME_DATE": "game_date", "MATCHUP": "matchup",
    "WL": "wl", "MIN": "minutes", "PTS": "pts", "REB": "reb", "AST": "ast",
    "FG3M": "fg3m", "STL": "stl", "BLK": "blk", "TOV": "tov",
    "FGA": "fga", "FTA": "fta",
}
_OPPONENT = re.compile(r"(?:vs\.|@)\s*(\S+)\s*$")


class NbaDataError(Exception):
    pass


def season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def current_season(today: dt.date) -> str:
    start_year = today.year if today.month >= SEASON_STARTS_IN_MONTH else today.year - 1
    return season_label(start_year)


def previous_season(season: str) -> str:
    return season_label(int(season[:4]) - 1)


def _season_end(season: str) -> dt.datetime:
    month, day = SEASON_ENDS
    return dt.datetime(int(season[:4]) + 1, month, day)


def normalize_player_games(raw: pd.DataFrame, season: str) -> pd.DataFrame:
    """Rename to snake_case, derive home/opponent, and sort chronologically."""
    games = raw.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())].copy()
    games["game_date"] = pd.to_datetime(games["game_date"])
    games["minutes"] = pd.to_numeric(games["minutes"], errors="coerce")
    games["is_home"] = games["matchup"].str.contains("vs.", regex=False)
    games["opponent"] = games["matchup"].str.extract(_OPPONENT, expand=False)
    games["season"] = season
    return games.sort_values(["player_id", "game_date", "game_id"]).reset_index(drop=True)


def fetch_season_from_api(season: str) -> pd.DataFrame:
    """Every regular-season player-game for `season` (one request)."""
    from nba_api.stats.endpoints import leaguegamelog

    log = leaguegamelog.LeagueGameLog(
        season=season,
        player_or_team_abbreviation="P",
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return log.get_data_frames()[0]


def _cache_is_usable(path: Path, season: str, today: dt.date) -> bool:
    if not path.exists():
        return False
    modified = path.stat().st_mtime
    if season != current_season(today):
        # a completed season only counts if it was saved after it ended
        return modified >= _season_end(season).timestamp()
    return time.time() - modified < CURRENT_SEASON_MAX_AGE_SECONDS


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["game_date"])


def load_season(
    season: str,
    *,
    today: dt.date | None = None,
    fetcher: Callable[[str], pd.DataFrame] = fetch_season_from_api,
    directory: Path | None = None,
) -> pd.DataFrame:
    """Normalized player-games for one season, from cache when valid.

    If a refresh fails but an older cache exists, the older data is
    returned (with a warning) rather than failing the whole app.
    """
    today = today or dt.date.today()
    directory = directory or NBA_DIR
    path = directory / f"games_{season}.csv"
    if _cache_is_usable(path, season, today):
        return _read(path)
    try:
        games = normalize_player_games(fetcher(season), season)
    except Exception as exc:  # network, HTTP, or parsing problems
        if path.exists():
            logger.warning("NBA refresh for %s failed (%s); using stale cache", season, exc)
            return _read(path)
        raise NbaDataError(f"Could not fetch NBA {season} game logs: {exc}") from exc
    directory.mkdir(parents=True, exist_ok=True)
    games.to_csv(path, index=False)
    return games
