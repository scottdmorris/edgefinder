"""The settle job keeps the public record current: the README table and the published
fingerprint are refreshed each morning, and only those two files are committed and pushed."""

import datetime as dt
import importlib.util
import subprocess
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TODAY = dt.date(2026, 11, 14)
README = """# Title

intro

<!-- record:start -->
old table
<!-- record:end -->

caveat stays
"""


@pytest.fixture
def publish():
    spec = importlib.util.spec_from_file_location("publish_record_under_test",
                                                  SCRIPTS / "publish_record.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def settled(version, day, result="win"):
    return {"model_version": version, "result": result, "pnl_units": 0.9 if result == "win" else -1.0,
            "clv_pct": 1.0, "book": "fanduel", "stat": "points", "status": "settled",
            "pick_side": "over", "game_date": day}


LEDGER = pd.DataFrame([settled("ewma-v1", "2026-11-04"), settled("ewma-v1", "2026-11-12", "loss")])


def test_the_readme_record_is_replaced_between_its_markers_and_nothing_else(publish, tmp_path):
    path = tmp_path / "README.md"
    path.write_text(README, encoding="utf-8")
    assert publish.refresh_readme(path, LEDGER, TODAY) is True
    text = path.read_text(encoding="utf-8")
    assert "old table" not in text and "| Simple (`ewma-v1`) | 2 | 1-1 |" in text
    assert "2 game days graded (2026-11-04 to 2026-11-12), as of 2026-11-14." in text
    assert text.startswith("# Title\n\nintro\n\n<!-- record:start -->\n")
    assert text.endswith("<!-- record:end -->\n\ncaveat stays\n")


def test_refreshing_twice_changes_nothing_the_second_time(publish, tmp_path):
    path = tmp_path / "README.md"
    path.write_text(README, encoding="utf-8")
    publish.refresh_readme(path, LEDGER, TODAY)
    assert publish.refresh_readme(path, LEDGER, TODAY) is False


def test_a_readme_without_the_markers_is_left_alone(publish, tmp_path):
    path = tmp_path / "README.md"
    path.write_text("no markers here\n", encoding="utf-8")
    with pytest.raises(ValueError):
        publish.refresh_readme(path, LEDGER, TODAY)
    assert path.read_text(encoding="utf-8") == "no markers here\n"


class Git:
    """Records git calls; `staged` says whether the files had changes to commit."""

    def __init__(self, staged=True, fail=None):
        self.calls, self.staged, self.fail = [], staged, fail

    def __call__(self, args, **kwargs):
        self.calls.append(args[1:])
        code = 0
        if args[1] == "diff":
            code = 1 if self.staged else 0
        if self.fail and args[1] == self.fail:
            raise subprocess.CalledProcessError(1, args, stderr="rejected")
        return subprocess.CompletedProcess(args, code, "", "")


def test_only_the_named_files_are_committed_then_pushed(publish, tmp_path):
    git = Git()
    files = [Path("README.md"), Path("record/DIGESTS.md")]
    assert publish.commit_and_push(tmp_path, files, "docs: record", run=git) == "pushed"
    commit = next(c for c in git.calls if c[0] == "commit")
    assert commit[-3:] == ["--", "README.md", "record/DIGESTS.md"]       # never anything else
    assert git.calls[-1][0] == "push"


def test_nothing_new_retries_push_without_another_commit(publish, tmp_path):
    git = Git(staged=False)
    assert publish.commit_and_push(tmp_path, [Path("README.md")], "docs: record", run=git) \
        == "nothing new"
    assert [c[0] for c in git.calls] == ["add", "diff", "push"]


def test_a_rejected_push_is_reported_not_hidden(publish, tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        publish.commit_and_push(tmp_path, [Path("README.md")], "docs: record", run=Git(fail="push"))


def test_a_record_that_does_not_match_its_log_is_never_published(publish, tmp_path, monkeypatch):
    class Unsound:
        intact = False

    class Audit:
        clean = True

    monkeypatch.setattr(publish.verify_record, "checked_ledger", lambda **kwargs: (None, Unsound(), Audit()))
    git = Git()
    assert "not published" in publish.run(TODAY, repo=tmp_path, run=git)
    assert git.calls == []


def test_failed_push_can_be_retried_after_commit_without_new_file_changes(publish, tmp_path):
    files = [Path("README.md"), Path("record/DIGESTS.md")]
    with pytest.raises(subprocess.CalledProcessError):
        publish.commit_and_push(tmp_path, files, "docs: record", run=Git(fail="push"))
    retry = Git(staged=False)
    publish.commit_and_push(tmp_path, files, "docs: record", run=retry)
    assert [call[0] for call in retry.calls] == ["add", "diff", "push"]


# A publish cut off at 9:00 is finished by a later snapshot run, without recomputing the
# fingerprint and without touching anything the owner changed or committed by hand.

DIGESTS = "| Day | Entries | Fingerprint |\n|---|---:|---|\n| 2026-11-21 | 10 | `aaa` |\n"
NEW_ROW = "| 2026-11-22 | 12 | `bbb` |\n"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repos(tmp_path):
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(repo))
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    git(repo, "checkout", "-q", "-b", "main")
    (repo / "record").mkdir()
    (repo / "README.md").write_text(README, encoding="utf-8", newline="\n")
    (repo / "record" / "DIGESTS.md").write_text(DIGESTS, encoding="utf-8", newline="\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "start")
    git(repo, "push", "-q", "-u", "origin", "main")
    return origin, repo


def stage_cut_off_publish(repo: Path, readme: str = README.replace("old table", "new table")) -> None:
    (repo / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    (repo / "record" / "DIGESTS.md").write_text(DIGESTS + NEW_ROW, encoding="utf-8", newline="\n")
    git(repo, "add", "README.md", "record/DIGESTS.md")


def test_nothing_waiting_does_nothing(publish, repos):
    assert publish.retry_unpublished(repos[1]) is None


def test_a_cut_off_publish_is_committed_as_staged_and_pushed(publish, repos):
    origin, repo = repos
    stage_cut_off_publish(repo)
    line = publish.retry_unpublished(repo)
    assert line.startswith("Record published on retry") and "2026-11-22" in line
    assert git(origin, "log", "-1", "--format=%s", "main").strip() == "docs: record as of 2026-11-22"
    assert "`bbb`" in git(origin, "show", "main:record/DIGESTS.md")     # the staged fingerprint, as is
    assert git(repo, "status", "--porcelain") == ""


def test_owner_edits_outside_the_record_table_are_never_swept_in(publish, repos):
    origin, repo = repos
    stage_cut_off_publish(repo, README.replace("old table", "new table").replace("intro", "my edit"))
    assert "skipped" in publish.retry_unpublished(repo)
    assert git(origin, "log", "-1", "--format=%s", "main").strip() == "start"


def test_a_readme_edit_without_a_new_fingerprint_is_not_ours(publish, repos):
    origin, repo = repos
    (repo / "README.md").write_text(README.replace("intro", "my edit"), encoding="utf-8", newline="\n")
    assert publish.retry_unpublished(repo) is None
    assert git(origin, "log", "-1", "--format=%s", "main").strip() == "start"


def test_a_committed_record_whose_push_failed_is_pushed(publish, repos):
    origin, repo = repos
    stage_cut_off_publish(repo)
    git(repo, "commit", "-q", "-m", "docs: record as of 2026-11-22")
    assert publish.retry_unpublished(repo) == "Record pushed on retry."
    assert git(origin, "log", "-1", "--format=%s", "main").strip() == "docs: record as of 2026-11-22"


def test_the_owners_unpushed_commits_are_never_pushed(publish, repos):
    origin, repo = repos
    (repo / "notes.txt").write_text("mine", encoding="utf-8")
    git(repo, "add", "notes.txt")
    git(repo, "commit", "-q", "-m", "feat: my own work")
    assert publish.retry_unpublished(repo) is None
    assert git(origin, "log", "-1", "--format=%s", "main").strip() == "start"
