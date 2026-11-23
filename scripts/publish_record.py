"""Keep the public record current: refresh the README's record table and the published
fingerprint, then commit and push those two files and nothing else.

The settle job runs this each morning (nba_props_settle.py --publish), so the record on
GitHub never falls behind. It publishes nothing when the ledger no longer matches its log.

Usage:  python scripts/publish_record.py
"""

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from edgefinder.data import nba_snapshot_plan  # noqa: E402
from edgefinder.tracking import nba_paper  # noqa: E402

import readme_results  # noqa: E402  (same folder)
import verify_record  # noqa: E402  (same folder)

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
START, END = "<!-- record:start -->", "<!-- record:end -->"
GIT_TIMEOUT_SECONDS = 120


def record_block(ledger: pd.DataFrame, today: dt.date) -> str:
    """The README's record table and one line saying what it covers."""
    days = sorted(ledger.loc[ledger["status"] == "settled", "game_date"].astype(str).unique())
    covers = (f"{len(days)} game days graded ({days[0]} to {days[-1]}), as of {today.isoformat()}."
              if days else f"No game days graded yet, as of {today.isoformat()}.")
    return f"{readme_results.table(ledger)}\n\n{covers}"


def refresh_readme(path: Path, ledger: pd.DataFrame, today: dt.date) -> bool:
    """Rewrite what sits between the record markers. Returns whether anything changed."""
    text = path.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        raise ValueError(f"{path.name} needs exactly one {START} ... {END} pair")
    head, rest = text.split(START)
    _, tail = rest.split(END)
    updated = f"{head}{START}\n{record_block(ledger, today)}\n{END}{tail}"
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def commit_and_push(repo: Path, files: list[Path], message: str, run=subprocess.run) -> str:
    """Commit only `files` (anything else staged or changed is left alone) and push.
    Returns "pushed" or "nothing new"; a failing git command raises."""
    names = [file.as_posix() for file in files]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}     # never wait for a password prompt

    def git(*args: str, check: bool = True):
        return run(["git", *args], cwd=repo, env=env, check=check, capture_output=True,
                   text=True, timeout=GIT_TIMEOUT_SECONDS)

    git("add", "--", *names)
    if git("diff", "--cached", "--quiet", "--", *names, check=False).returncode == 0:
        git("push")  # retry a previously committed record whose push failed
        return "nothing new"
    git("commit", "-m", message, "--", *names)
    git("push")
    return "pushed"


RECORD_FILES = (Path("README.md"), Path("record") / "DIGESTS.md")
RECORD_SUBJECT = "docs: record as of "


def _outside_record(text: str) -> str:
    text = text.replace("\r\n", "\n")
    if START not in text or END not in text:
        return text
    head, rest = text.split(START, 1)
    return head + rest.split(END, 1)[1]


def retry_unpublished(repo: Path = REPO, run=subprocess.run) -> str | None:
    """Finish a morning publish that was cut off: commit the record exactly as the job staged
    it (the fingerprint is never recomputed, so it still matches the morning post) and push.
    Acts only on what is plainly the job's own work. A README edit outside the record table,
    or any unpushed commit that is not a record commit, is left for the owner. Returns one
    line for the log, or None when nothing is waiting."""
    names = [file.as_posix() for file in RECORD_FILES]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    def git(*args: str, check: bool = True):
        return run(["git", *args], cwd=repo, env=env, check=check, capture_output=True,
                   text=True, timeout=GIT_TIMEOUT_SECONDS)

    changed = git("status", "--porcelain", "--", *names).stdout.splitlines()
    if changed:
        if not any(line.endswith(names[1]) for line in changed):
            return None                          # no new fingerprint: an edit by hand, not ours
        before = git("show", f"HEAD:{names[0]}").stdout
        now = (repo / RECORD_FILES[0]).read_text(encoding="utf-8")
        old_rows = git("show", f"HEAD:{names[1]}").stdout.replace("\r\n", "\n")
        rows = (repo / RECORD_FILES[1]).read_text(encoding="utf-8").replace("\r\n", "\n")
        if _outside_record(before) != _outside_record(now) or not rows.startswith(old_rows):
            return "Record retry skipped: the README or fingerprint file has other edits."
        day = rows.strip().splitlines()[-1].split("|")[1].strip()
        outcome = commit_and_push(repo, list(RECORD_FILES), f"{RECORD_SUBJECT}{day}", run=run)
        return f"Record published on retry ({outcome}) for {day}."
    ahead = git("log", "@{u}..HEAD", "--format=%s", check=False)
    subjects = ahead.stdout.split("\n") if ahead.returncode == 0 else []
    subjects = [subject for subject in subjects if subject]
    if not subjects or not all(subject.startswith(RECORD_SUBJECT) for subject in subjects):
        return None
    touched = {name for name in git("diff", "--name-only", "@{u}..HEAD").stdout.split("\n") if name}
    if not touched <= set(names):
        return None
    git("push")
    return "Record pushed on retry."


def run(today: dt.date, repo: Path = REPO, run=subprocess.run) -> str:
    """Refresh and publish. Returns one line for the settle report."""
    verification, audit = verify_record.check()
    if not (verification.intact and audit.clean):
        return "Record not published: the ledger does not match its log."
    digests = repo / "record" / "DIGESTS.md"
    readme = repo / "README.md"
    verify_record.write_digest(verification, today, digests)
    refresh_readme(readme, nba_paper.load_ledger(), today)
    outcome = commit_and_push(repo, [readme.relative_to(repo), digests.relative_to(repo)],
                              f"docs: record as of {today.isoformat()}", run=run)
    return f"Record published ({outcome}): {verification.entries} log entries."


def main() -> None:
    print(run(dt.datetime.now(nba_snapshot_plan.EASTERN).date()))


if __name__ == "__main__":
    main()
