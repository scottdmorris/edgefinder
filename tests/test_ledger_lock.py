"""One job at a time on a ledger, so a settle's rewrite never drops a snapshot's new rows."""

import os
import time

import pytest

from edgefinder.data import safe_write
from edgefinder.tracking import nba_alt


def test_a_second_job_waits_for_the_lock_and_gives_up_after_its_wait(tmp_path):
    ledger = tmp_path / "ledger.csv"
    with safe_write.locked(ledger):
        assert (tmp_path / "ledger.csv.lock").exists()
        with pytest.raises(TimeoutError):
            with safe_write.locked(ledger, wait=0.3):
                pass
    assert not (tmp_path / "ledger.csv.lock").exists()     # released
    with safe_write.locked(ledger, wait=0.3):              # free again
        pass


def test_a_lock_left_by_a_job_that_died_is_cleared(tmp_path):
    lock = tmp_path / "ledger.csv.lock"
    lock.write_text("123")
    old = time.time() - 3600
    os.utime(lock, (old, old))
    with safe_write.locked(tmp_path / "ledger.csv", wait=0.3, stale=60):
        pass


def test_the_lock_is_released_when_the_work_fails(tmp_path):
    with pytest.raises(RuntimeError):
        with safe_write.locked(tmp_path / "ledger.csv"):
            raise RuntimeError("boom")
    assert not (tmp_path / "ledger.csv.lock").exists()


def test_appends_wait_while_a_settle_holds_the_ledger(tmp_path, monkeypatch):
    ledger = tmp_path / "alt.csv"
    monkeypatch.setattr(safe_write, "LOCK_WAIT_SECONDS", 0.3)
    with safe_write.locked(ledger):
        with pytest.raises(TimeoutError):
            nba_alt.append_rows([], path=ledger)
