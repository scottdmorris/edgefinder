"""Check that the paper ledger has not been changed since it was logged.

Walks the pick log (every fingerprint is recomputed), compares the ledger with it, and prints
what it finds. With --write-digest it also appends today's fingerprint to record/DIGESTS.md;
commit and push that file and GitHub's commit time becomes an independent timestamp.

Usage:  python scripts/verify_record.py [--write-digest | --recover-unlogged]
Exit code 0 when the log is intact and the ledger matches it, 1 otherwise.
"""

import argparse
import datetime as dt
import sys
import shutil
from tempfile import TemporaryDirectory
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import nba_snapshot_plan, safe_write  # noqa: E402
from edgefinder.tracking import nba_paper, pick_chain  # noqa: E402

DIGESTS = Path(__file__).resolve().parents[1] / "record" / "DIGESTS.md"


def check(ledger_path: Path | None = None) -> tuple[pick_chain.Verification, pick_chain.Audit]:
    ledger_path = ledger_path or nba_paper.LEDGER_PATH
    chain = pick_chain.chain_path_for(ledger_path)
    return pick_chain.verify(chain), pick_chain.audit(nba_paper.load_ledger(ledger_path), chain)


def recover_unlogged(ledger_path: Path) -> int:
    """Append a dated import for missing rows. Refuse to repair any other discrepancy."""
    chain = pick_chain.chain_path_for(ledger_path)
    with safe_write.locked(ledger_path):
        verification, audit = check(ledger_path)
        if not verification.intact or not verification.entries:
            raise ValueError("Recovery requires an existing intact chain.")
        if audit.clean:
            return 0
        entries = pick_chain.load(chain)
        seen = {entry["key"] for entry in entries if entry["kind"] == pick_chain.PICK}
        results = {entry["key"] for entry in entries if entry["kind"] == pick_chain.RESULT}
        ledger = nba_paper.load_ledger(ledger_path)
        missing = [row for row in ledger.to_dict("records") if pick_chain.row_key(row) not in seen]
        recovered_at = dt.datetime.now(dt.timezone.utc)
        with TemporaryDirectory(dir=chain.parent) as temporary:
            staged = Path(temporary) / chain.name
            shutil.copyfile(chain, staged)
            pick_chain.record_picks(staged, missing, recovered_at, imported=True)
            missing_results = [row for row in missing if row["status"] in ("settled", "void")
                               and pick_chain.row_key(row) not in results]
            pick_chain.record_results(staged, missing_results, recovered_at, imported=True)
            if not pick_chain.verify(staged).intact or not pick_chain.audit(ledger, staged).clean:
                raise ValueError("Recovery would leave other audit discrepancies.")
            safe_write.write_text(chain, staged.read_text(encoding="utf-8"))
        return len(missing)


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
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--write-digest", action="store_true")
    operation.add_argument("--recover-unlogged", action="store_true",
                           help="Import missing ledger rows with their actual recovery timestamp")
    args = parser.parse_args()
    if args.recover_unlogged:
        try:
            count = recover_unlogged(nba_paper.LEDGER_PATH)
        except ValueError as error:
            parser.exit(1, f"{error}\n")
        print(f"Imported {count} previously unlogged ledger rows.")
    verification, audit = check()
    print(f"Log: {verification.entries} entries ({verification.imported} marked as imports), "
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
