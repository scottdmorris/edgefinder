"""Never let tests write to the live offered-slip database."""
import pytest

from edgefinder.tracking import suggested_record


@pytest.fixture(autouse=True)
def no_real_propline(tmp_path, monkeypatch):
    """No test may spend the real PropLine key or write the real PropLine archive."""
    from edgefinder.data import propline
    monkeypatch.delenv("PROPLINE_API_KEY", raising=False)
    monkeypatch.setattr(propline, "KEY_PATH", tmp_path / "propline_key.txt")
    monkeypatch.setattr(propline, "LINES_PATH", tmp_path / "nba_propline_lines.csv")


@pytest.fixture(autouse=True)
def isolated_suggestion_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(suggested_record, "DB_PATH", tmp_path / "suggestions.sqlite3")
