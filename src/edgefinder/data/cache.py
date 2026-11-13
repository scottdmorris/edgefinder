"""Tiny JSON file cache so free-tier API quotas are not wasted and the
dashboard loads fast."""

import hashlib
import json
import time
from pathlib import Path

from . import safe_write

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache"


def _path_for(key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    return CACHE_DIR / f"{digest}.json"


def get(key: str, max_age_seconds: float):
    path = _path_for(key)
    if not path.exists():
        return None
    try:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if time.time() - wrapper["saved_at"] > max_age_seconds:
        return None
    return wrapper["value"]


def put(key: str, value) -> None:
    wrapper = {"saved_at": time.time(), "value": value}
    safe_write.write_text(_path_for(key), json.dumps(wrapper))
