"""User settings persisted between sessions (bankroll, Kelly fraction)."""

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "config.json"

DEFAULTS = {"bankroll": 500.0, "kelly_multiplier": 0.25}


def load_settings() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    try:
        stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    return {**DEFAULTS, **stored}


def save_settings(settings: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
