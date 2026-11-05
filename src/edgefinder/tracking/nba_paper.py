"""Paper-trade ledger for NBA player-point props. No money is staked.

Every priced line gets a row at its early snapshot, with the model's
probability and the market's own devigged probability, so calibration is
scored on ALL lines, not just the picks. A line becomes a pick when the
blended probability (model blended toward the market, as on the MLB
board) clears MIN_EV_TO_RECORD at FanDuel's price.

Settlement fills in the actual points, grades picks at a flat 1 unit, and
attaches closing-line information from the late snapshot. Props void when
the player doesn't play.

CLV is the change in implied probability of the pick's own price when the
line didn't move; when it did, it is reported as points of line movement
in the pick's favour.
"""

import csv
import datetime as dt
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from ..betting import negbin
from ..betting.ev import ev_per_unit
from ..betting.odds_math import american_to_decimal, devig_two_way, implied_prob
from ..models import nba_stat_model
from ..models.nba_points import MODEL_DISPERSION, MODEL_VERSION

LEDGER_PATH = Path(__file__).resolve().parents[3] / "data" / "nba_paper_log.csv"
MODEL_WEIGHT = 0.30       # same market anchoring as the MLB board
MIN_EV_TO_RECORD = 0.02

COLUMNS = [
    "recorded_at", "game_date", "event_id", "commence_time", "home", "away",
    "player", "player_id", "line", "over_odds", "under_odds",
    "model_version", "model_mean", "model_p_over", "fair_p_over",
    "pick_side", "pick_odds", "pick_ev",
    "status", "actual", "went_over", "result", "pnl_units",
    "closing_line", "closing_over_odds", "closing_under_odds",
    "clv_pct", "line_move",
    "stat", "book",
]
_TEXT_COLUMNS = ["status", "result", "pick_side", "went_over", "stat", "book"]
DEFAULT_STAT = "points"
DEFAULT_BOOK = "fanduel"
# rows written before these columns existed were all FanDuel points lines
_LEGACY_DEFAULTS = {"stat": DEFAULT_STAT, "book": DEFAULT_BOOK}


def build_ledger_rows(
    event: dict,
    lines: list[dict],
    predictions: dict[str, dict],
    recorded_at: str,
    game_date: str,
    *,
    model_version: str = MODEL_VERSION,
    dispersion: float | Callable = MODEL_DISPERSION,
    stat: str = DEFAULT_STAT,
    book: str = DEFAULT_BOOK,
) -> list[dict]:
    """One row per line we can price. Skipped: players with no projection,
    lines missing a side, and whole-number lines (a push would need its
    own handling, and FanDuel almost always posts half points).

    Several models can price the same line: each writes its own rows,
    tagged with its `model_version` and using its own `dispersion`."""
    rows = []
    for item in lines:
        prediction = predictions.get(item["player"])
        over_odds, under_odds, point = item["over_odds"], item["under_odds"], item["line"]
        if prediction is None or over_odds is None or under_odds is None:
            continue
        if float(point).is_integer():
            continue
        fair_over, _ = devig_two_way(implied_prob(over_odds), implied_prob(under_odds))
        model_over = float(negbin.over_prob(point, prediction["mean"], dispersion))
        blend_over = MODEL_WEIGHT * model_over + (1 - MODEL_WEIGHT) * fair_over
        ev_over = ev_per_unit(blend_over, american_to_decimal(over_odds))
        ev_under = ev_per_unit(1 - blend_over, american_to_decimal(under_odds))
        side, odds, ev = (("over", over_odds, ev_over) if ev_over >= ev_under
                          else ("under", under_odds, ev_under))
        is_pick = ev >= MIN_EV_TO_RECORD
        rows.append({column: None for column in COLUMNS} | {
            "recorded_at": recorded_at, "game_date": game_date,
            "event_id": event["event_id"], "commence_time": event["commence_time"],
            "home": event["home"], "away": event["away"],
            "player": item["player"], "player_id": prediction["player_id"],
            "line": point, "over_odds": over_odds, "under_odds": under_odds,
            "model_version": model_version, "model_mean": prediction["mean"],
            "model_p_over": model_over, "fair_p_over": fair_over,
            "pick_side": side if is_pick else None,
            "pick_odds": odds if is_pick else None,
            "pick_ev": ev if is_pick else None,
            "status": "pending", "stat": stat, "book": book,
        })
    return rows


def load_ledger(path: Path | None = None) -> pd.DataFrame:
    path = path or LEDGER_PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS).astype({c: object for c in _TEXT_COLUMNS})
    ledger = pd.read_csv(path)
    for column, default in _LEGACY_DEFAULTS.items():
        if column not in ledger.columns:
            ledger[column] = default
        ledger[column] = ledger[column].fillna(default)
    return ledger.astype({c: object for c in _TEXT_COLUMNS})


def _upgrade_file(path: Path) -> None:
    """Rewrite an older ledger file with the current columns before new rows
    are appended, so the header and the rows can never disagree."""
    with path.open(encoding="utf-8") as handle:
        header = handle.readline().strip().split(",")
    if header != COLUMNS:
        save_ledger(load_ledger(path).reindex(columns=COLUMNS), path)


def save_ledger(ledger: pd.DataFrame, path: Path | None = None) -> None:
    path = path or LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(path, index=False)


def append_rows(rows: list[dict], path: Path | None = None) -> int:
    """Add rows not already recorded for the same game, player, line, model,
    stat and book. Returns how many were new."""
    path = path or LEDGER_PATH
    existing = load_ledger(path)
    seen = set(map(_row_key, existing.to_dict("records")))
    fresh = []
    for row in rows:
        key = _row_key(row)
        if key not in seen:
            seen.add(key)
            fresh.append(row)
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    if not is_new:
        _upgrade_file(path)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerows(fresh)
    return len(fresh)


def _row_key(row: dict) -> tuple:
    return (row["event_id"], row["player"], float(row["line"]), row["model_version"],
            row.get("stat") or DEFAULT_STAT, row.get("book") or DEFAULT_BOOK)


def settle(
    ledger: pd.DataFrame,
    games: pd.DataFrame,
    snapshots: pd.DataFrame,
    today: dt.date,
) -> pd.DataFrame:
    """Return a copy of the ledger with finished games settled and closing
    information attached. `games` needs player_id, game_date and pts."""
    out = ledger.astype({c: object for c in _TEXT_COLUMNS}).copy()
    values = _stat_values(out, games)

    for index in out.index[out["status"] == "pending"]:
        row = out.loc[index]
        stat_values = values.get(row["stat"])
        if stat_values is None:
            continue                         # the game logs don't cover this stat
        key = (int(row["player_id"]), str(row["game_date"]))
        if key in stat_values:
            _settle_row(out, index, row, stat_values[key])
        elif str(row["game_date"]) < today.isoformat():
            out.loc[index, "status"] = "void"  # the player never got on the floor
            out.loc[index, "pnl_units"] = 0.0

    _attach_closing(out, snapshots)
    return out


def _stat_values(ledger: pd.DataFrame, games: pd.DataFrame) -> dict[str, dict]:
    """For each stat in the ledger that the game logs cover: what every
    player did on every date."""
    values = {}
    for stat in ledger["stat"].dropna().unique():
        column = nba_stat_model.STATS[stat].column
        if column in games.columns:
            values[stat] = {
                (int(row.player_id), row.game_date.strftime("%Y-%m-%d")): float(getattr(row, column))
                for row in games.itertuples()
            }
    return values


def _settle_row(out: pd.DataFrame, index, row: pd.Series, actual: float) -> None:
    went_over = actual > float(row["line"])
    out.loc[index, "status"] = "settled"
    out.loc[index, "actual"] = actual
    out.loc[index, "went_over"] = went_over
    if pd.isna(row["pick_side"]):
        return
    won = (row["pick_side"] == "over") == went_over
    out.loc[index, "result"] = "win" if won else "loss"
    out.loc[index, "pnl_units"] = (
        american_to_decimal(float(row["pick_odds"])) - 1.0 if won else -1.0)


def _attach_closing(out: pd.DataFrame, snapshots: pd.DataFrame) -> None:
    late = snapshots[snapshots["phase"] == "late"].sort_values("fetched_at")
    if late.empty:
        return
    closing = late.groupby(["event_id", "player"]).tail(1).set_index(["event_id", "player"])
    # the late snapshots are FanDuel points lines, so they only close those rows
    closable = (out["status"] != "pending") & (out["stat"] == DEFAULT_STAT) \
        & (out["book"] == DEFAULT_BOOK)
    for index in out.index[closable]:
        row = out.loc[index]
        key = (row["event_id"], row["player"])
        if key not in closing.index:
            continue
        snap = closing.loc[key]
        out.loc[index, "closing_line"] = snap["line"]
        out.loc[index, "closing_over_odds"] = snap["over_odds"]
        out.loc[index, "closing_under_odds"] = snap["under_odds"]
        if pd.isna(row["pick_side"]):
            continue
        is_over = row["pick_side"] == "over"
        out.loc[index, "line_move"] = (
            snap["line"] - row["line"] if is_over else row["line"] - snap["line"])
        closing_odds = snap["over_odds" if is_over else "under_odds"]
        if snap["line"] == row["line"] and pd.notna(closing_odds):
            placed = implied_prob(float(row["pick_odds"]))
            out.loc[index, "clv_pct"] = (
                (implied_prob(float(closing_odds)) - placed) / placed * 100.0)


def scope(ledger: pd.DataFrame, model_version: str | None = None, stat: str | None = None,
          book: str | None = None) -> pd.DataFrame:
    """Only the rows for one model, stat and/or book; None leaves that
    dimension unfiltered."""
    for column, wanted in (("model_version", model_version), ("stat", stat), ("book", book)):
        if wanted is not None:
            ledger = ledger[ledger[column] == wanted]
    return ledger


def load_fanduel_ledger(path: Path | None = None) -> pd.DataFrame:
    """The ledger's FanDuel rows only. The record views read this so prices from other
    books (Kalshi) never count towards the per-model FanDuel record or accuracy."""
    return scope(load_ledger(path), book=DEFAULT_BOOK)


def summary(ledger: pd.DataFrame, model_version: str | None = None, stat: str | None = None,
            book: str | None = None) -> dict:
    picks = scope(ledger, model_version, stat, book)
    picks = picks[picks["pick_side"].notna()]
    settled = picks[picks["status"] == "settled"]
    units = float(pd.to_numeric(settled["pnl_units"], errors="coerce").sum())
    clv = pd.to_numeric(picks["clv_pct"], errors="coerce").dropna()
    return {
        "picks": len(picks),
        "settled": len(settled),
        "record": f"{(settled['result'] == 'win').sum()}-{(settled['result'] == 'loss').sum()}",
        "units": units,
        "roi_pct": units / len(settled) * 100.0 if len(settled) else 0.0,
        "avg_clv_pct": float(clv.mean()) if len(clv) else None,
        "avg_line_move": _mean_or_none(picks["line_move"]),
    }


def _mean_or_none(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if len(values) else None


def calibration_summary(ledger: pd.DataFrame, model_version: str | None = None,
                        stat: str | None = None, book: str | None = None) -> dict:
    """Brier score of the model's P(over) vs the market's devigged P(over)
    on every settled line. Lower is better; the model only has something
    to offer if its score beats the market's."""
    ledger = scope(ledger, model_version, stat, book)
    settled = ledger[ledger["status"] == "settled"].dropna(subset=["went_over"])
    if settled.empty:
        return {"n": 0, "brier_model": None, "brier_market": None}
    outcome = settled["went_over"].astype(float)
    return {
        "n": len(settled),
        "brier_model": float(((settled["model_p_over"].astype(float) - outcome) ** 2).mean()),
        "brier_market": float(((settled["fair_p_over"].astype(float) - outcome) ** 2).mean()),
    }


def compare_versions(ledger: pd.DataFrame, stat: str | None = None,
                     book: str | None = None) -> pd.DataFrame:
    """Head-to-head Brier scores, one row per model version, on only the
    settled lines that EVERY version priced, so no model is flattered by
    an easier set of lines. The market's score on the same lines is
    included. Empty when fewer than two versions have settled lines."""
    columns = ["n", "brier_model", "brier_market"]
    settled = scope(ledger, stat=stat, book=book)
    settled = settled[settled["status"] == "settled"].dropna(subset=["went_over"])
    versions = settled["model_version"].nunique()
    if versions < 2:
        return pd.DataFrame(columns=columns)
    # older ledgers have no stat or book column; they were all one line type
    key = [c for c in ("event_id", "player", "line", "stat", "book") if c in settled.columns]
    priced_by_all = settled.groupby(key)["model_version"].nunique()
    shared = priced_by_all[priced_by_all == versions].index.to_frame(index=False)
    common = settled.merge(shared, on=key)
    if common.empty:
        return pd.DataFrame(columns=columns)
    rows = {}
    for version, group in common.groupby("model_version"):
        outcome = group["went_over"].astype(float)
        rows[version] = {
            "n": len(group),
            "brier_model": float(((group["model_p_over"].astype(float) - outcome) ** 2).mean()),
            "brier_market": float(((group["fair_p_over"].astype(float) - outcome) ** 2).mean()),
        }
    return pd.DataFrame(rows).T[columns]
