import datetime as dt
import json
from zoneinfo import ZoneInfo

from edgefinder.data import job_health as jh

ET = ZoneInfo("America/New_York")


def at(day, hour, minute=0):
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=ET)


def beat(when, outcome="ok", detail=""):
    return {"ran_at": when.astimezone(dt.timezone.utc).isoformat(), "outcome": outcome,
            "detail": detail}


def test_a_heartbeat_is_written_and_read_back(tmp_path):
    path = tmp_path / "beats.json"
    jh.record("snapshot", jh.OK, "2 games", path, now=dt.datetime(2026, 11, 5, 23, 30,
                                                                    tzinfo=dt.timezone.utc))
    jh.record("settle", jh.FAILED, "no data", path)
    beats = jh.load(path)
    assert beats["snapshot"]["outcome"] == "ok" and beats["snapshot"]["detail"] == "2 games"
    assert beats["snapshot"]["ran_at"].startswith("2026-11-05T23:30")
    assert beats["settle"]["outcome"] == "failed"          # a second job keeps the first


def test_a_missing_or_broken_file_reads_as_no_heartbeats(tmp_path):
    assert jh.load(tmp_path / "nope.json") == {}
    broken = tmp_path / "bad.json"
    broken.write_text("{not json", encoding="utf-8")
    assert jh.load(broken) == {}
    broken.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert jh.load(broken) == {}


def test_a_job_never_fails_over_its_own_heartbeat(tmp_path):
    blocked = tmp_path / "a_file"
    blocked.write_text("x", encoding="utf-8")
    jh.record("snapshot", jh.OK, path=blocked / "inside.json")        # parent is a file: cannot write


def test_a_recent_snapshot_reads_as_fine_with_the_time_in_eastern():
    health = jh.snapshot_health({"snapshot": beat(at(5, 18, 30))}, at(5, 18, 50))
    assert health == jh.Health("ok", "Lines last checked Nov 5, 6:30 PM ET")


def test_two_missed_runs_is_behind_and_three_hours_is_stopped_but_only_while_runs_are_due():
    last = {"snapshot": beat(at(5, 18, 30))}
    assert jh.snapshot_health(last, at(5, 19, 40)).level == "ok"      # 70 min: still within slack
    assert jh.snapshot_health(last, at(5, 19, 50)).level == "warn"    # 80 min: behind
    stopped = jh.snapshot_health(last, at(5, 21, 40))                 # 3 h 10 min
    assert stopped.level == "bad" and "not being recorded" in stopped.text
    # overnight no run is expected, so a stale heartbeat is not an alarm
    assert jh.snapshot_health(last, at(6, 3, 0)).level == "ok"
    assert jh.snapshot_health(last, at(5, 12, 30)).level == "ok"      # before the first run


def test_a_failed_snapshot_is_bad_with_the_reason_whatever_the_hour():
    health = jh.snapshot_health({"snapshot": beat(at(5, 18, 30), jh.FAILED, "API down")},
                                at(6, 3, 0))
    assert health.level == "bad" and "API down" in health.text


def test_no_heartbeat_or_an_unreadable_one_is_a_warning_not_an_error():
    assert jh.snapshot_health({}, at(5, 18)).level == "warn"
    assert jh.snapshot_health({"snapshot": {"ran_at": "garbage"}}, at(5, 18)).level == "warn"


def test_grading_is_overdue_only_after_nine_plus_a_grace_period():
    yesterday = {"settle": beat(at(5, 9, 0))}
    assert jh.settle_health(yesterday, at(6, 8, 0)).level == "ok"          # not yet due today
    assert jh.settle_health(yesterday, at(6, 9, 30)).level == "ok"         # inside the grace
    assert jh.settle_health(yesterday, at(6, 10, 0)).level == "warn"       # 9:00 + 45 min passed
    assert jh.settle_health({"settle": beat(at(6, 9, 0))}, at(6, 15, 0)).level == "ok"


def test_a_failed_grading_run_is_bad_and_a_missing_one_is_a_warning():
    assert jh.settle_health({"settle": beat(at(6, 9, 0), jh.FAILED, "x")}, at(6, 15)).level == "bad"
    assert jh.settle_health({}, at(6, 15)).level == "warn"


def test_the_worst_problem_wins_and_nothing_wrong_gives_none():
    ok, warn, bad = jh.Health("ok", "a"), jh.Health("warn", "b"), jh.Health("bad", "c")
    assert jh.worst(ok, warn, bad) is bad and jh.worst(ok, warn) is warn
    assert jh.worst(ok, ok) is None
