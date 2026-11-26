"""Recoverable publication of the paper ledger and its audit chain.

Call under the existing ledger lock. Both complete replacement files are
flushed before the readiness marker is published. After that point, any
interruption can be replayed without rebuilding or dating an audit entry again.
"""

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path

from ..data import safe_write


def _digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _fingerprint(path: Path) -> str | None:
    return _digest(path) if path.exists() else None


def _directory(ledger: Path) -> Path:
    return ledger.with_name(ledger.name + ".pending")


def pending(ledger: Path) -> bool:
    return (_directory(ledger) / "ready.json").is_file()


def _clear(directory: Path) -> None:
    for name in ("ready.json", "ledger.csv", "chain.jsonl", "ready.json.marker.tmp"):
        (directory / name).unlink(missing_ok=True)
    directory.rmdir()


def recover(ledger: Path, chain: Path) -> bool:
    directory = _directory(ledger)
    if not directory.exists():
        return False
    ready = directory / "ready.json"
    if not ready.exists():
        _clear(directory)
        return False

    manifest = json.loads(ready.read_text(encoding="utf-8"))
    files = [(directory / name, target, manifest[name])
             for name, target in (("ledger.csv", ledger), ("chain.jsonl", chain))]
    # Validate both sides before replacing either. An absent staged file is
    # expected after promotion, but the destination must match the journal.
    for staged, target, expected in files:
        if staged.exists() and _digest(staged) != expected["after"]:
            raise ValueError(f"Interrupted ledger write cannot be recovered: staged {staged.name} differs.")
        state = "before" if staged.exists() else "after"
        if _fingerprint(target) != expected[state]:
            raise ValueError(f"Interrupted ledger write cannot be recovered: {target.name} differs.")
    for staged, target, _ in files:
        if staged.exists():
            safe_write.replace_file(staged, target)
    _clear(directory)
    return True


def commit(ledger: Path, chain: Path, prepare: Callable[[Path, Path], None]) -> None:
    directory = _directory(ledger)
    directory.mkdir()
    staged = directory / "ledger.csv", directory / "chain.jsonl"
    prepare(*staged)
    for path in staged:
        with path.open("r+b") as handle:
            os.fsync(handle.fileno())
    manifest = {path.name: {"before": _fingerprint(target), "after": _digest(path)}
                for path, target in zip(staged, (ledger, chain), strict=True)}
    marker = directory / "ready.json.marker.tmp"
    with marker.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest))
        handle.flush()
        os.fsync(handle.fileno())
    safe_write.replace_file(marker, directory / "ready.json")
    recover(ledger, chain)
