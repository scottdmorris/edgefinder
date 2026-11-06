"""Corrections to each model's points chances, by player role.

The models' chances were measured against what happened (scripts/nba_calibration_by_line.py)
and were too sure about bench players. scripts/nba_recalibration_fit.py fits, for each model and
role, a curve from what the model said to what happened, and saves it to recalibration.json next
to this file. `calibrate` applies it.

It is used where a decision is made (pricing a parlay leg, suggesting a slip), not in the ledger:
the record keeps each model's raw chances, so it still judges the models as they are.
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

CURVES_PATH = Path(__file__).with_name("recalibration.json")
RECENT_GAMES = 10
# a player's role, from his average minutes over his last 10 games
ROLES = (("bench", 0.0, 18.0), ("rotation", 18.0, 28.0), ("starter", 28.0, 99.0))
ROLE_NAMES = tuple(name for name, _, _ in ROLES)
GRID = np.linspace(0.02, 0.98, 49)        # where each curve is stored


def role_for(minutes) -> str | None:
    """'bench', 'rotation' or 'starter'; None when the minutes are unknown."""
    if minutes is None:
        return None
    try:
        value = float(minutes)
    except (TypeError, ValueError):
        return None
    if np.isnan(value):
        return None
    for name, low, high in ROLES:
        if low <= value < high:
            return name
    return ROLES[-1][0]


@lru_cache(maxsize=1)
def load_curves(path: str = str(CURVES_PATH)) -> dict:
    """{model version: {role: {"x": [...], "y": [...]}}}; empty when no curves were fitted."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def calibrate(version: str, chance: float, minutes, curves: dict | None = None) -> float:
    """The corrected chance of reaching a points line, for this model and the player's role.
    Unchanged when there is no curve for the model or the role, or the minutes are unknown."""
    role = role_for(minutes)
    curve = (curves if curves is not None else load_curves()).get(version, {}).get(role)
    if curve is None:
        return float(chance)
    return float(np.interp(float(chance), curve["x"], curve["y"]))
