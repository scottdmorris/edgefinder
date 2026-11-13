"""Replace a file in one step.

The jobs rewrite whole files (the ledgers when settling, the heartbeat, the caches). Writing
straight over the original means a crash, a full disk or a sync client grabbing the file
mid-write leaves it cut short. Here the new contents go to a temporary file beside the
original, which is then swapped in; the original is either the old version or the new one,
never part of each.
"""

import os
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd

REPLACE_ATTEMPTS = 5
REPLACE_WAIT_SECONDS = 0.2     # Windows refuses the swap while another program has the file open


def _replace(path: Path, write: Callable[[Path], None], wait: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        write(temporary)
        for attempt in range(1, REPLACE_ATTEMPTS + 1):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS:
                    raise
                time.sleep(wait)
    finally:
        temporary.unlink(missing_ok=True)


def write_text(path: Path, text: str, wait: float = REPLACE_WAIT_SECONDS) -> None:
    _replace(path, lambda target: target.write_text(text, encoding="utf-8"), wait)


def write_csv(frame: pd.DataFrame, path: Path, wait: float = REPLACE_WAIT_SECONDS) -> None:
    _replace(path, lambda target: frame.to_csv(target, index=False), wait)
