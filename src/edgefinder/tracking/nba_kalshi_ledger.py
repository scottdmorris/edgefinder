"""Record Kalshi prices in the paper ledger (book="kalshi").

Kalshi lists "N+" contracts for points, rebounds, assists and threes. Each
liquid one becomes the same kind of ledger row FanDuel's lines do: an over
at N - 0.5 priced at the yes ask, an under priced at the no ask, tagged
book="kalshi" and the right stat, so the rows can be graded and bet-built
like any other.

JOINING A MARKET TO A GAME. A Kalshi ticker carries the date and the two
teams' tricodes (away then home) but no tip-off time and no game id. A
market joins to the schedule event whose away and home teams have those
tricodes and whose Eastern tip-off date is the ticker's date. The NBA has
no doubleheaders, so that triple is one game; if a schedule ever held two
matches, the markets are skipped as ambiguous rather than guessed. A
tricode that matches no scheduled team (including one Kalshi spells
differently from the NBA) is skipped and counted, never forced.

ONLY LIQUID MARKETS (kalshi.is_liquid) are recorded: an empty or one-sided
book has an ask that means nothing. PRICES ARE BEFORE KALSHI'S TRADING FEES,
so every Kalshi probability and pick EV here flatters the bettor.

A row's key is (event, player, line, model, stat, book), so re-running a
snapshot adds nothing: the first liquid price seen for a contract is the
one recorded (the early price, the one a pick is made at).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..data import kalshi, nba_players, nba_snapshot_plan
from ..models import nba_stat_model
from . import nba_paper

log = logging.getLogger(__name__)

# projections[event_id][stat][player name as Kalshi spells it] -> {player_id, mean}
Projections = dict[str, dict[str, dict[str, dict]]]


@dataclass(frozen=True)
class KalshiModel:
    """A model that prices Kalshi lines: its ledger version, the dispersion
    for each stat it covers, and project(event, stat, names)."""
    version: str
    dispersions: dict[str, float]
    project: Callable[[dict, str, list[str]], dict[str, dict]]


@dataclass
class JoinResult:
    by_event: dict[str, list[dict]] = field(default_factory=dict)
    unmatched: list[dict] = field(default_factory=list)   # no scheduled game has these teams/date
    ambiguous: list[dict] = field(default_factory=list)   # more than one does
    illiquid: int = 0                                     # skipped for a thin or one-sided book


def fetch_kalshi_rows(fetch: Callable[[str], dict] = kalshi.fetch_series) -> list[dict]:
    """Every parsed market, one network call per series. A series that fails
    is skipped with a one-line warning; the others still come back, and
    nothing raised here can reach the FanDuel snapshot."""
    rows: list[dict] = []
    for series in kalshi.SERIES_STATS:
        try:
            rows.extend(kalshi.parse_markets(fetch(series)))
        except kalshi.KalshiDataError as exc:
            log.warning("Kalshi %s unavailable, skipped: %s", series, exc)
    return rows


def _game_key(away: str | None, home: str | None, game_date: str) -> tuple:
    return (away, home, game_date)


def join_to_events(kalshi_rows: list[dict], events: list[dict]) -> JoinResult:
    """Keep the liquid rows and attach each to its game by AWAY+HOME tricode
    and date. `events` is the schedule to record (the Odds API shape:
    event_id, commence_time, home and away full team names)."""
    index: dict[tuple, list[dict]] = {}
    for event in events:
        key = _game_key(nba_players.team_abbreviation(event["away"]),
                        nba_players.team_abbreviation(event["home"]),
                        nba_snapshot_plan.tip_date(event))
        index.setdefault(key, []).append(event)

    result = JoinResult()
    for row in kalshi_rows:
        if row.get("is_liquid") is not True:
            result.illiquid += 1
            continue
        matches = index.get(_game_key(row["away"], row["home"], row["game_date"]), [])
        if not matches or None in (row["away"], row["home"]):
            result.unmatched.append(row)
        elif len(matches) > 1:
            result.ambiguous.append(row)
        else:
            result.by_event.setdefault(matches[0]["event_id"], []).append(row)
    return result


def _lines_by_stat(rows: list[dict]) -> dict[str, list[dict]]:
    by_stat: dict[str, list[dict]] = {}
    for line in kalshi.to_lines(rows):
        by_stat.setdefault(line["stat"], []).append(line)
    return by_stat


def player_names(rows: list[dict], stat: str) -> list[str]:
    """Distinct players with a row for this stat, in first-seen order."""
    return list(dict.fromkeys(r["player"] for r in rows if r["stat"] == stat))


def build_kalshi_ledger_rows(
    kalshi_rows: list[dict],
    events: list[dict],
    projections: Projections,
    recorded_at: str,
    *,
    model_version: str,
    dispersions: dict[str, float] | None = None,
) -> list[dict]:
    """Ledger-shaped rows for the liquid Kalshi markets that join to a game
    in `events`. A stat with no dispersion, a player with no projection, or
    a market missing either ask produces no row."""
    dispersions = dispersions or {s: stat.dispersion for s, stat in nba_stat_model.STATS.items()}
    joined = join_to_events(kalshi_rows, events)
    events_by_id = {e["event_id"]: e for e in events}
    ledger_rows: list[dict] = []
    for event_id, rows in joined.by_event.items():
        event = events_by_id[event_id]
        for stat, lines in _lines_by_stat(rows).items():
            if stat not in dispersions:
                continue
            ledger_rows += nba_paper.build_ledger_rows(
                event, lines, projections.get(event_id, {}).get(stat, {}), recorded_at,
                nba_snapshot_plan.tip_date(event), model_version=model_version,
                dispersion=dispersions[stat], stat=stat, book=kalshi.BOOK)
    return ledger_rows


def record_kalshi(
    kalshi_rows: list[dict],
    events: list[dict],
    models: list[KalshiModel],
    recorded_at: str,
    path: Path | None = None,
) -> dict[str, int]:
    """Price tonight's liquid Kalshi markets with each model and append the
    new rows. One model failing never stops the others. Returns the new rows
    each model version added (0 for one that failed)."""
    joined = join_to_events(kalshi_rows, events)
    log.info("Kalshi: %d games matched, %d markets skipped (thin book), %d unmatched, %d ambiguous",
             len(joined.by_event), joined.illiquid, len(joined.unmatched), len(joined.ambiguous))
    for code in sorted({f"{r['away']}@{r['home']} {r['game_date']}" for r in joined.unmatched}):
        log.info("Kalshi: no scheduled game for %s", code)
    events_by_id = {e["event_id"]: e for e in events}
    added: dict[str, int] = {}
    for model in models:
        try:
            projections: Projections = {}
            for event_id, rows in joined.by_event.items():
                for stat in model.dispersions:
                    names = player_names(rows, stat)
                    if names:
                        projections.setdefault(event_id, {})[stat] = model.project(
                            events_by_id[event_id], stat, names)
            ledger_rows = build_kalshi_ledger_rows(
                [r for rows in joined.by_event.values() for r in rows], events, projections,
                recorded_at, model_version=model.version, dispersions=model.dispersions)
            added[model.version] = nba_paper.append_rows(ledger_rows, path=path)
        except Exception:
            log.exception("Kalshi model %s failed; the other models are unaffected", model.version)
            added[model.version] = 0
    return added
