"""The small file cache, and where the Odds API key is read from."""

import pytest

from edgefinder.data import cache, odds_api


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(odds_api, "KEY_FILE", tmp_path / "key.txt")
    monkeypatch.delenv("ODDS_API_KEY", raising=False)


def test_a_saved_value_comes_back_while_it_is_fresh():
    cache.put("k", {"a": 1})
    assert cache.get("k", max_age_seconds=60) == {"a": 1}


def test_a_value_older_than_asked_for_is_not_returned(monkeypatch):
    cache.put("k", 1)
    saved = cache.time.time()
    monkeypatch.setattr(cache.time, "time", lambda: saved + 120)
    assert cache.get("k", max_age_seconds=60) is None
    assert cache.get("k", max_age_seconds=float("inf")) == 1


def test_a_missing_or_damaged_entry_reads_as_nothing():
    assert cache.get("never saved", 60) is None
    cache.put("k", 1)
    cache._path_for("k").write_text("{not json", encoding="utf-8")
    assert cache.get("k", 60) is None


def test_no_key_anywhere_is_none():
    assert odds_api.get_api_key() is None


def test_the_key_file_is_read_and_trimmed():
    odds_api.KEY_FILE.write_text("  abc123\n", encoding="utf-8")
    assert odds_api.get_api_key() == "abc123"


def test_an_empty_key_file_is_no_key():
    odds_api.KEY_FILE.write_text("\n", encoding="utf-8")
    assert odds_api.get_api_key() is None


def test_the_environment_variable_wins_over_the_file(monkeypatch):
    odds_api.KEY_FILE.write_text("from-file", encoding="utf-8")
    monkeypatch.setenv("ODDS_API_KEY", " from-env ")
    assert odds_api.get_api_key() == "from-env"


def test_the_quota_is_whatever_was_last_stored():
    assert odds_api.get_quota() is None
    cache.put(odds_api.QUOTA_CACHE_KEY, {"remaining": "356", "used": "144"})
    assert odds_api.get_quota() == {"remaining": "356", "used": "144"}
