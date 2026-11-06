"""Check that the paper ledger has not been changed since it was logged.

Walks the pick log (every fingerprint is recomputed), compares the ledger with it, and prints
what it finds. With --write-digest it also appends today's fingerprint to record/DIGESTS.md;
commit and push that file and GitHub's commit time becomes an independent timestamp.

Usage:  python scripts/verify_record.py [--write-digest]
Exit code 0 when the log is intact and the ledger matches it, 1 otherwise.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import nba_snapshot_plan  # noqa: E402
from edgefinder.tracking import nba_paper, pick_chain  # noqa: E402

DIGESTS = Path(__file__).resolve().parents[1] / "record" / "DIGESTS.md"


def check(ledger_path: Path | None = None) -> tuple[pick_chain.Verification, pick_chain.Audit]:
    ledger_path = ledger_path or nba_paper.LEDGER_PATH
    chain = pick_chain.chain_path_for(ledger_path)
    return pick_chain.verify(chain), pick_chain.audit(nba_paper.load_ledger(ledger_path), chain)


def write_digest(verification: pick_chain.Verification, today: dt.date,
                 path: Path = DIGESTS) -> bool:
    """Append today's line unless the file already has this exact state. Returns whether it did."""
    line = pick_chain.digest_line(verification, today)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if f"| {verification.entries} | `{verification.head}` |" in existing:
        return False
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--write-digest", action="store_true")
    args = parser.parse_args()
    verification, audit = check()
    print(f"Log: {verification.entries} entries ({verification.imported} imported when it began), "
          f"{'INTACT' if verification.intact else 'BROKEN'}")
    print(f"Latest fingerprint: {verification.head}")
    print(f"Ledger: {audit.matched} of {audit.rows} rows match the log")
    for problem in (verification.problems + audit.problems)[:pick_chain.MAX_PROBLEMS_SHOWN]:
        print("  PROBLEM:", problem)
    sound = verification.intact and audit.clean
    if args.write_digest:
        if not sound:
            print("Not writing a digest: the record does not match its log.")
        else:
            today = dt.datetime.now(nba_snapshot_plan.EASTERN).date()
            added = write_digest(verification, today)
            print("Wrote a line to record/DIGESTS.md: commit and push it to publish."
                  if added else "record/DIGESTS.md already has this exact state.")
    sys.exit(0 if sound else 1)


if __name__ == "__main__":
    main()
