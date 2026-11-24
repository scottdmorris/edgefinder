"""A paper trial of FanDuel's "X+" lines for rebounds, assists and threes ("Miller 6+
rebounds"), read from PropLine's milestone markets at the early snapshot, priced by the
Simple model (the one that projects every stat) and graded from box scores.

It is kept in its own file, apart from the points X+ ledger, so nothing that shows or
publishes the record (the board, the Record screen, the X posts, the trials) can pick it
up. It exists to find out whether these bets are worth suggesting; nothing suggests them.

The pick rule is the points X+ rule without its ban on the Simple model: that ban was
earned on points, and whether it holds for the other stats is what this trial measures.
"""

import csv
import datetime as dt
import math
from pathlib import Path

import pandas as pd

from ..betting.ev import ev_per_unit
from ..betting.odds_math import american_to_decimal, implied_prob
from ..data import safe_write
from ..models import nba_stat_model
from . import nba_alt, settlement
from .nba_paper import MAX_DISAGREEMENT, MIN_EV_TO_RECORD, MIN_MODEL_P, MODEL_WEIGHT, tipped_off

LEDGER_PATH = Path(__file__).resolve().parents[3] / "data" / "nba_alt_stats_log.csv"
COLUMNS = nba_alt.COLUMNS + ["stat"]
STATS = ("rebounds", "assists", "threes")


def dispersion(stat: str) -> float:
    return nba_stat_model.STATS[stat].dispersion


def is_pick(ev: float, model_p: float, market_p: float) -> bool:
    return (ev >= MIN_EV_TO_RECORD and model_p >= MIN_MODEL_P
            and abs(model_p - market_p) <= MAX_DISAGREEMENT)


def build_rows(event: dict, lines: list[dict], predictions: dict[str, dict], recorded_at: str,
               game_date: str, *, model_version: str, stat: str) -> list[dict]:
    """One row per rung we can price. `lines` hold player, line (5.5 means 6+) and
    over_odds; FanDuel lists only the over, so the market chance keeps its vig, the
    conservative direction. Nothing is recorded once the game has tipped off."""
    if stat not in STATS or tipped_off(recorded_at, event["commence_time"]):
        return []
    rows = []
    for item in lines:
        prediction = predictions.get(item["player"])
        point, odds = item["line"], item["over_odds"]
        if prediction is None or odds is None or float(point).is_integer():
            continue
        threshold = math.ceil(point)
        model_p = nba_alt.p_at_least(threshold, prediction["mean"], dispersion(stat))
        market_p = implied_prob(odds)
        blend = MODEL_WEIGHT * model_p + (1 - MODEL_WEIGHT) * market_p
        ev = ev_per_unit(blend, american_to_decimal(odds))
        picked = is_pick(ev, model_p, market_p)
        rows.append({column: None for column in COLUMNS} | {
            "recorded_at": recorded_at, "game_date": game_date,
            "event_id": event["event_id"], "commence_time": event["commence_time"],
            "home": event["home"], "away": event["away"],
            "player": item["player"], "player_id": prediction["player_id"],
            "threshold": threshold, "over_odds": odds,
            "model_version": model_version, "model_mean": prediction["mean"],
            "model_p": model_p, "market_p": market_p,
            "pick_ev": ev if picked else None, "is_pick": picked, "status": "pending",
            "stat": stat,
        })
    return rows


def load_ledger(path: Path | None = None) -> pd.DataFrame:
    path = path or LEDGER_PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path, dtype={"status": object, "result": object, "stat": object})


def save_ledger(ledger: pd.DataFrame, path: Path | None = None) -> None:
    nba_alt.save_ledger(ledger, path or LEDGER_PATH)


def _key(row) -> tuple:
    return (str(row["event_id"]), str(row["player"]), str(row["stat"]),
            int(row["threshold"]), str(row["model_version"]))


def append_rows(rows: list[dict], path: Path | None = None) -> int:
    """Add rows not already recorded for the same game, player, stat, rung and model."""
    path = path or LEDGER_PATH
    with safe_write.locked(path):     # never while a settle is rewriting the file
        return _append_rows_unlocked(rows, path)


def _append_rows_unlocked(rows: list[dict], path: Path) -> int:
    seen = {_key(row) for row in load_ledger(path).to_dict("records")}
    fresh = []
    for row in rows:
        if _key(row) not in seen:
            seen.add(_key(row))
            fresh.append(row)
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerows(fresh)
    return len(fresh)


def settle(ledger: pd.DataFrame, games: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """Grade finished games on each row's own stat at a flat 1 unit; void players who
    never played."""
    out = ledger.astype({"result": object, "status": object}).copy()
    played = {(int(row["player_id"]), pd.Timestamp(row["game_date"]).strftime("%Y-%m-%d")): row
              for row in games.to_dict("records")}
    complete = settlement.completed_games(games)
    for index in out.index[out["status"] == "pending"]:
        row = out.loc[index]
        box = played.get((int(row["player_id"]), str(row["game_date"])))
        if box is not None:
            actual = float(box[nba_stat_model.STATS[row["stat"]].column])
            if math.isnan(actual):
                continue                 # the box score isn't filled in yet: grade it next run
            won = actual >= float(row["threshold"])
            out.loc[index, "status"] = "settled"
            out.loc[index, "actual"] = actual
            if str(row["is_pick"]) == "True":
                out.loc[index, "result"] = "win" if won else "loss"
                out.loc[index, "pnl_units"] = (
                    american_to_decimal(float(row["over_odds"])) - 1.0 if won else -1.0)
        elif settlement.can_void(row, today, complete):
            out.loc[index, "status"] = "void"
            out.loc[index, "pnl_units"] = 0.0
    return out


def report_lines(ledger: pd.DataFrame) -> list[str]:
    """The settle log's lines: each stat's picks, record and units."""
    if ledger.empty:
        return []
    lines = ["", f"X+ trial, other stats (paper only, never suggested): {len(ledger)} prices"]
    for stat in STATS:
        part = ledger[ledger["stat"] == stat]
        if part.empty:
            continue
        s = nba_alt.summary(part)
        lines.append(f"  {stat:9s} {s['picks']} picks, {s['settled']} settled, record "
                     f"{s['record']}, {s['units']:+.2f} units ({s['roi_pct']:+.1f}% ROI)")
    return lines
