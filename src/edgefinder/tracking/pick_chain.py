"""A tamper-evident log of the paper ledger.

The ledger is a plain CSV that anyone with the file can edit. This keeps a second,
append-only file beside it: one entry per ledger row when it is written, and one more
when its result is filled in. Each entry carries a SHA-256 fingerprint of its own contents
AND the previous entry's fingerprint, so changing, removing or reordering any past entry
breaks every fingerprint after it.

What it proves, and what it does not:
- It proves the entries are in the order they were written and unchanged since, IF the
  latest fingerprint (the "head") was kept somewhere the operator cannot quietly rewrite.
  `scripts/verify_record.py --write-digest` produces a line to commit to the public repo,
  where the commit time is a witness the operator does not control.
- On its own, anyone who can edit the ledger can also rebuild the whole chain. Publishing
  the head is what stops that.
- `audit` compares the ledger with the chain and reports rows that were edited, deleted or
  never logged. It cannot say when an entry was written beyond the clock of the machine
  that wrote it.

Rows that were already in the ledger when this started are imported once and marked so;
everything after is logged as it happens.
"""

import datetime as dt
import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

GENESIS = "0" * 64
PICK = "pick"
RESULT = "result"

# what is fixed at the moment a row is recorded
PICK_FIELDS = (
    "recorded_at", "game_date", "event_id", "commence_time", "home", "away", "player",
    "player_id", "line", "over_odds", "under_odds", "model_version", "model_mean",
    "model_p_over", "fair_p_over", "pick_side", "pick_odds", "pick_ev", "stat", "book")
# what is filled in once the game is over
RESULT_FIELDS = ("status", "actual", "went_over", "result", "pnl_units")
# columns rows written before they existed are assumed to have
LEGACY = {"stat": "points", "book": "fanduel"}
MAX_PROBLEMS_SHOWN = 20


def chain_path_for(ledger_path: Path) -> Path:
    """The chain that goes with a ledger file: nba_paper_log.csv -> nba_paper_log.chain.jsonl."""
    return ledger_path.with_suffix(".chain.jsonl")


# ---- the chain itself ---------------------------------------------------------------------

def _clean(value):
    """One representation of a value, so the same row always hashes the same: missing is None,
    whole floats stay floats, text stays text."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):                      # numpy scalars
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    return None if text in ("", "nan", "None") else text


def canonical(body: dict) -> str:
    """The exact text that gets fingerprinted: sorted keys, no spaces."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(previous: str, body: dict) -> str:
    return hashlib.sha256((previous + "\n" + canonical(body)).encode("utf-8")).hexdigest()


def load(path: Path) -> list[dict]:
    """Every entry in the chain, in order; empty if there is no chain yet."""
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _append(path: Path, entries: list[dict]) -> None:
    """Add entries, each fingerprinted with the one before it."""
    existing = load(path)
    previous = existing[-1]["hash"] if existing else GENESIS
    seq = len(existing)
    lines = []
    for entry in entries:
        body = {**entry, "seq": seq, "prev": previous}
        previous = fingerprint(body["prev"], {k: v for k, v in body.items() if k != "prev"})
        lines.append(json.dumps({**body, "hash": previous}, sort_keys=True, separators=(",", ":"),
                                allow_nan=False))
        seq += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def _body(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k not in ("hash", "prev")}


# ---- what goes in an entry -----------------------------------------------------------------

def row_key(row) -> str:
    """The ledger's identity for a row: game, player, line, model, stat and book."""
    get = row.get if hasattr(row, "get") else (lambda k, d=None: row[k])
    stat = _clean(get("stat")) or LEGACY["stat"]
    book = _clean(get("book")) or LEGACY["book"]
    return "|".join([str(get("event_id")), str(get("player")), f"{float(get('line')):g}",
                     str(get("model_version")), str(stat), str(book)])


def _data(row, fields) -> dict:
    get = row.get if hasattr(row, "get") else (lambda k, d=None: row[k])
    data = {field_: _clean(get(field_)) for field_ in fields}
    for field_, default in LEGACY.items():
        if field_ in data and data[field_] is None:
            data[field_] = default
    return data


def _entry(kind: str, row, fields, now: dt.datetime, imported: bool) -> dict:
    return {"kind": kind, "key": row_key(row), "data": _data(row, fields),
            "at": now.isoformat(), "imported": imported}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def record_picks(path: Path, rows: list[dict], now: dt.datetime | None = None,
                 imported: bool = False) -> int:
    """Log newly written ledger rows (picks and non-picks alike, so nothing can be dropped
    quietly). Returns how many entries were added."""
    if not rows:
        return 0
    moment = now or _now()
    _append(path, [_entry(PICK, row, PICK_FIELDS, moment, imported) for row in rows])
    return len(rows)


def record_results(path: Path, rows: list[dict], now: dt.datetime | None = None,
                   imported: bool = False) -> int:
    """Log rows whose result has just been filled in."""
    if not rows:
        return 0
    moment = now or _now()
    _append(path, [_entry(RESULT, row, RESULT_FIELDS, moment, imported) for row in rows])
    return len(rows)


def ensure_started(chain_path: Path, ledger: pd.DataFrame, now: dt.datetime | None = None) -> bool:
    """Start the chain from a ledger that already has rows: import every row, then every
    result, marked as imported because they were not witnessed as they happened. Does nothing
    if the chain exists or the ledger is empty. Returns whether it started one."""
    if chain_path.exists() or ledger.empty:
        return False
    moment = now or _now()
    records = ledger.to_dict("records")
    record_picks(chain_path, records, moment, imported=True)
    done = [r for r in records if _clean(r.get("status")) in ("settled", "void")]
    record_results(chain_path, done, moment, imported=True)
    return True


def settlements(before: pd.DataFrame, after: pd.DataFrame) -> list[dict]:
    """The rows that were pending in `before` and have a result in `after` (same index)."""
    was_open = before["status"] == "pending"
    now_done = after.loc[before.index, "status"].isin(["settled", "void"])
    return after.loc[was_open & now_done].to_dict("records")


def record_settlements(chain_path: Path, before: pd.DataFrame, after: pd.DataFrame,
                       now: dt.datetime | None = None) -> int:
    """Log the results a settle run just filled in."""
    return record_results(chain_path, settlements(before, after), now)


# ---- checking ------------------------------------------------------------------------------

@dataclass
class Verification:
    intact: bool
    entries: int
    head: str
    imported: int
    first_at: str | None
    problems: list[str] = field(default_factory=list)


def verify(path: Path) -> Verification:
    """Walk the chain and recompute every fingerprint. Any change to a past entry, any removed
    or reordered entry, shows up as a problem at that point."""
    entries = load(path)
    previous, problems = GENESIS, []
    for position, entry in enumerate(entries):
        if entry.get("seq") != position:
            problems.append(f"entry {position}: out of order or missing (says {entry.get('seq')})")
        if entry.get("prev") != previous:
            problems.append(f"entry {position}: does not follow the entry before it")
        expected = fingerprint(entry.get("prev", ""), _body(entry))
        if entry.get("hash") != expected:
            problems.append(f"entry {position}: contents do not match its fingerprint")
        previous = entry.get("hash", "")
    return Verification(
        intact=not problems, entries=len(entries), head=entries[-1]["hash"] if entries else GENESIS,
        imported=sum(1 for e in entries if e.get("imported")),
        first_at=entries[0]["at"] if entries else None, problems=problems)


@dataclass
class Audit:
    rows: int
    matched: int
    problems: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.problems


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def _differences(logged: dict, current: dict) -> list[str]:
    return [name for name in logged if not _same(logged[name], current.get(name))]


def audit(ledger: pd.DataFrame, path: Path) -> Audit:
    """Compare the ledger with what the chain recorded: rows edited since they were logged,
    rows deleted, rows that were never logged, and results that disagree."""
    picks: dict[str, dict] = {}
    results: dict[str, dict] = {}
    problems: list[str] = []
    for entry in load(path):
        target = picks if entry["kind"] == PICK else results
        if entry["key"] in target:
            problems.append(f"{entry['kind']} logged twice for {entry['key']}")
        target.setdefault(entry["key"], entry["data"])

    matched = 0
    seen = set()
    for row in ledger.to_dict("records"):
        key = row_key(row)
        seen.add(key)
        if key not in picks:
            problems.append(f"not in the chain (never logged): {key}")
            continue
        changed = _differences(picks[key], _data(row, PICK_FIELDS))
        if changed:
            problems.append(f"edited after it was logged ({', '.join(changed)}): {key}")
            continue
        status = _clean(row.get("status"))
        if status in ("settled", "void"):
            logged = results.get(key)
            if logged is None:
                problems.append(f"result was never logged: {key}")
                continue
            changed = _differences(logged, _data(row, RESULT_FIELDS))
            if changed:
                problems.append(f"result differs from the one logged ({', '.join(changed)}): {key}")
                continue
        elif key in results:
            problems.append(f"has a logged result but the ledger says {status}: {key}")
            continue
        matched += 1
    for key in picks:
        if key not in seen:
            problems.append(f"deleted from the ledger: {key}")
    return Audit(rows=len(ledger), matched=matched, problems=problems)


def holds(path: Path, entries: int, head: str) -> bool:
    """Does this log contain a published state: its `entries`-th entry carries fingerprint
    `head`? This is what catches a log that was cut short or rewritten after the head was
    published, since a rewritten history cannot reproduce the old fingerprint."""
    chain = load(path)
    return entries >= 1 and len(chain) >= entries and chain[entries - 1]["hash"] == head


def published(digests: Path) -> list[tuple[str, int, str]]:
    """Every fingerprint recorded in a digest file, oldest first: (date, entries, head)."""
    if not digests.exists():
        return []
    found = []
    for line in digests.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[1].isdigit() and len(cells[2].strip("`")) == 64:
            found.append((cells[0], int(cells[1]), cells[2].strip("`")))
    return found


def check_published(path: Path, digests: Path) -> list[tuple[str, int, bool]]:
    """Does the log still contain each published state? [(date, entries, still_holds)]."""
    return [(date, count, holds(path, count, head)) for date, count, head in published(digests)]


def digest_line(verification: Verification, today: dt.date) -> str:
    """One line to publish: the date, how many entries, and the head fingerprint."""
    return f"| {today.isoformat()} | {verification.entries} | `{verification.head}` |"
