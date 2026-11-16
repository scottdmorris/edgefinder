"""Never let tests write to the live offered-slip database."""
import pytest

from edgefinder.tracking import suggested_record


@pytest.fixture(autouse=True)
def isolated_suggestion_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(suggested_record, "DB_PATH", tmp_path / "suggestions.sqlite3")
