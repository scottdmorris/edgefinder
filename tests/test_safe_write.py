"""Files the jobs rewrite whole (ledgers, the heartbeat, caches) are written beside the
original and swapped in, so a crash mid-write can never leave half a ledger."""

import pandas as pd
import pytest

from edgefinder.data import safe_write


def test_text_is_written_and_no_temporary_file_is_left(tmp_path):
    path = tmp_path / "deep" / "file.json"
    safe_write.write_text(path, "hello")
    assert path.read_text(encoding="utf-8") == "hello"
    assert [p.name for p in path.parent.iterdir()] == ["file.json"]


def test_a_table_round_trips(tmp_path):
    path = tmp_path / "ledger.csv"
    safe_write.write_csv(pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}), path)
    assert pd.read_csv(path).to_dict("list") == {"a": [1, 2], "b": ["x", "y"]}


def test_a_failed_write_leaves_the_old_file_untouched(tmp_path):
    path = tmp_path / "ledger.csv"
    path.write_text("old\n", encoding="utf-8")

    class Broken(pd.DataFrame):
        def to_csv(self, *args, **kwargs):
            raise OSError("disk full")

    with pytest.raises(OSError):
        safe_write.write_csv(Broken({"a": [1]}), path)
    assert path.read_text(encoding="utf-8") == "old\n"
    assert [p.name for p in tmp_path.iterdir()] == ["ledger.csv"]


def test_a_briefly_locked_file_is_retried(tmp_path, monkeypatch):
    path = tmp_path / "file.txt"
    path.write_text("old", encoding="utf-8")
    real, calls = safe_write.os.replace, []

    def flaky(source, target):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("in use")        # another program has it open (Windows)
        real(source, target)

    monkeypatch.setattr(safe_write.os, "replace", flaky)
    safe_write.write_text(path, "new", wait=0)
    assert path.read_text(encoding="utf-8") == "new" and len(calls) == 3


def test_a_file_that_stays_locked_raises_and_keeps_the_old_contents(tmp_path, monkeypatch):
    path = tmp_path / "file.txt"
    path.write_text("old", encoding="utf-8")

    def locked(source, target):
        raise PermissionError("in use")

    monkeypatch.setattr(safe_write.os, "replace", locked)
    with pytest.raises(PermissionError):
        safe_write.write_text(path, "new", wait=0)
    assert path.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["file.txt"]
