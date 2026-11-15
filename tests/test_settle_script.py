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


def test_with_publish_the_record_line_is_added_to_the_report(script, monkeypatch, tmp_path):
    monkeypatch.setattr(script, "build_report", lambda today: "Ledger: 41 lines")
    monkeypatch.setattr(script, "publish_line", lambda today: "Record published (pushed)")
    log = tmp_path / "jobs.log"
    monkeypatch.setattr(script.sys, "argv", ["nba_props_settle.py", "--publish", "--log-file", str(log)])
    script.main()
    assert "Record published (pushed)" in log.read_text(encoding="utf-8")
    assert job_health.load(script.job_health.HEARTBEAT_PATH)["settle"]["outcome"] == "ok"


def test_a_publishing_failure_is_reported_but_never_fails_the_settle(script, monkeypatch, tmp_path):
    import publish_record

    def rejected(today, **kwargs):
        raise RuntimeError("push rejected")

    monkeypatch.setattr(publish_record, "run", rejected)
    assert script.publish_line(None) == "Record not published: RuntimeError: push rejected"


def test_without_publish_nothing_is_published(script, monkeypatch):
    monkeypatch.setattr(script, "build_report", lambda today: "Ledger: 41 lines")
    monkeypatch.setattr(script, "publish_line", lambda today: pytest.fail("published"))
    script.main()


def test_the_fair_close_line_reads_plainly_and_says_when_there_is_nothing(script):
    assert script.fair_close_text({"clv_novig_n": 0}) == "vs fair close: n/a"
    assert script.fair_close_text({"clv_novig_n": 40, "avg_clv_novig_pct": -1.234,
                                   "beat_fair_close_pct": 42.4}) == \
        "vs fair close -1.23% on 40, beat it 42%"
