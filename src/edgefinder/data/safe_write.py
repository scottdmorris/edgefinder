"""Replace a file in one step.

The jobs rewrite whole files (the ledgers when settling, the heartbeat, the caches). Writing
straight over the original means a crash, a full disk or a sync client grabbing the file
mid-write leaves it cut short. Here the new contents go to a temporary file beside the
original, which is then swapped in; the original is either the old version or the new one,
never part of each.
"""

import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

REPLACE_ATTEMPTS = 5
REPLACE_WAIT_SECONDS = 0.2     # Windows refuses the swap while another program has the file open
LOCK_WAIT_SECONDS = 120        # how long a job waits for another job's turn with a ledger
LOCK_STALE_SECONDS = 900       # a lock this old was left by a job that died; it is cleared
LOCK_POLL_SECONDS = 0.2


@contextmanager
def locked(path: Path, wait: float | None = None,
           stale: float | None = None) -> Iterator[None]:
    """One job at a time on a ledger. The snapshot appends rows while the settle reads the
    whole file, grades it and writes it back; without this, rows appended in between are
    overwritten. Not re-entrant: never take the same lock twice in one job."""
    wait = LOCK_WAIT_SECONDS if wait is None else wait
    stale = LOCK_STALE_SECONDS if stale is None else stale
    lock = path.with_name(f"{path.name}.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait
    while True:
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > stale:
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue                       # released between our two looks
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{path.name} is in use by another job") from None
            time.sleep(LOCK_POLL_SECONDS)
            continue
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        break
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _replace(path: Path, write: Callable[[Path], None], wait: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        write(temporary)
        replace_file(temporary, path, wait)
    finally:
        temporary.unlink(missing_ok=True)


def replace_file(source: Path, target: Path, wait: float = REPLACE_WAIT_SECONDS) -> None:
    """Move a prepared file into place. Keep the source if replacement fails."""
    for attempt in range(1, REPLACE_ATTEMPTS + 1):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS:
                raise
            time.sleep(wait)


def write_text(path: Path, text: str, wait: float = REPLACE_WAIT_SECONDS) -> None:
    _replace(path, lambda target: target.write_text(text, encoding="utf-8"), wait)


def write_csv(frame: pd.DataFrame, path: Path, wait: float = REPLACE_WAIT_SECONDS) -> None:
    _replace(path, lambda target: frame.to_csv(target, index=False), wait)
