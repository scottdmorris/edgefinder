import importlib.util
from pathlib import Path

import pytest

from edgefinder.data import job_health


@pytest.fixture
def script(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "nba_props_settle.py"
    spec = importlib.util.spec_from_file_location("nba_props_settle_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.job_health, "HEARTBEAT_PATH", tmp_path / "heartbeat.json")
    monkeypatch.setattr(module.sys, "argv", ["nba_props_settle.py"])
    return module


def test_a_good_grading_run_reports_ok_with_the_first_line_of_the_report(script, monkeypatch):
    monkeypatch.setattr(script, "build_report", lambda today: "Ledger: 41 lines\nmore detail")
    script.main()
    beat = job_health.load(script.job_health.HEARTBEAT_PATH)["settle"]
    assert beat["outcome"] == "ok" and beat["detail"] == "Ledger: 41 lines"


def test_a_crashed_grading_run_reports_failed_and_still_exits_nonzero(script, monkeypatch):
    def boom(today):
        raise RuntimeError("game logs missing")

    monkeypatch.setattr(script, "build_report", boom)
    with pytest.raises(SystemExit):
        script.main()
    beat = job_health.load(script.job_health.HEARTBEAT_PATH)["settle"]
    assert beat["outcome"] == "failed" and "game logs missing" in beat["detail"]
