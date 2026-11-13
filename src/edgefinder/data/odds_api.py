"""The Odds API (the-odds-api.com): where the key lives and how much quota is left.

The requests themselves are made by nba_props, which never puts the request URL in an error
message, because the URL carries the key.

Set the key via the ODDS_API_KEY environment variable or a data/odds_api_key.txt file
(git-ignored). The free tier is 500 requests a month; every response's quota headers are
stored so the jobs can stop before it runs out.
"""

import os
from pathlib import Path

from . import cache

BASE = "https://api.the-odds-api.com/v4"
REQUEST_TIMEOUT = 20
KEY_FILE = Path(__file__).resolve().parents[3] / "data" / "odds_api_key.txt"
QUOTA_CACHE_KEY = "odds_api_quota"


def get_api_key() -> str | None:
    env_key = os.environ.get("ODDS_API_KEY", "").strip()
    if env_key:
        return env_key
    if KEY_FILE.exists():
        file_key = KEY_FILE.read_text(encoding="utf-8").strip()
        if file_key:
            return file_key
    return None


def get_quota() -> dict | None:
    """Most recent quota headers: {'remaining': str, 'used': str}."""
    return cache.get(QUOTA_CACHE_KEY, float("inf"))
