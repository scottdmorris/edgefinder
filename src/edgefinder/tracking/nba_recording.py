"""Record every registered points model's view of a game's lines.

Several models can price the same line, each under its own version, so
the paper ledger becomes a live head-to-head. The rule that keeps it safe
to run unattended: one model failing never stops the others, so a broken
challenger can't take the original model's records down with it.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import nba_paper

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegisteredModel:
    version: str
    dispersion: float | Callable
    project: Callable[[dict, list[str]], dict[str, dict]]


def record_event(
    event: dict,
    lines: list[dict],
    models: list[RegisteredModel],
    recorded_at: str,
    game_date: str,
    path: Path | None = None,
) -> dict[str, int]:
    """Price one game's lines with each model. Returns how many new rows
    each model version added (0 for a model that failed)."""
    names = [line["player"] for line in lines]
    added: dict[str, int] = {}
    for model in models:
        try:
            projections = model.project(event, names)
            rows = nba_paper.build_ledger_rows(
                event, lines, projections, recorded_at, game_date,
                model_version=model.version, dispersion=model.dispersion)
            added[model.version] = nba_paper.append_rows(rows, path=path)
        except Exception:
            log.exception("model %s failed on %s @ %s; the other models are unaffected",
                          model.version, event["away"], event["home"])
            added[model.version] = 0
    return added
