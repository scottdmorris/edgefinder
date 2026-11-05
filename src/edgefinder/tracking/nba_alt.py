"""Paper tracking for "X+ points" bets (alternate lines), like "Jaylen Brown 15+".

The points models already predict a whole distribution, so any total can
be priced: P(points >= 15) is the chance of 15 or more. Two pieces live
here:

- a ladder that prices rungs for a player, with no API requests at all
- a ledger of FanDuel's real X+ prices, priced by every model and settled
  from box scores, recorded at the early snapshot only

FanDuel lists only the "over" side of an X+ bet, so there is no devigged
market probability. The market anchor is the price's raw implied
probability, vig included, which makes an edge look smaller than it is.
That is deliberate: it is the conservative direction.
"""

import csv
import datetime as dt
import logging
import math
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from ..betting import negbin
from ..betting.ev import ev_per_unit
from ..betting.odds_math import american_to_decimal, implied_prob
from ..models import nba_context_points, nba_context_v2, nba_minutes_points, nba_points
from .nba_paper import MIN_EV_TO_RECORD, MODEL_WEIGHT

log = logging.getLogger(__name__)

LEDGER_PATH = Path(__file__).resolve().parents[3] / "data" / "nba_alt_log.csv"
RUNGS = [5, 10, 15, 20, 25, 30, 35, 40]
DISPERSIONS = {
    nba_points.MODEL_VERSION: nba_points.MODEL_DISPERSION,
    nba_minutes_points.MODEL_VERSION: nba_minutes_points.MODEL_DISPERSION,
    nba_context_points.MODEL_VERSION: nba_context_points.MODEL_DISPERSION,
    nba_context_v2.MODEL_VERSION: nba_context_v2.MODEL_DISPERSION,
}
_MIN_PROB, _MAX_PROB = 0.001, 0.999
# The model's spread was fitted around the middle of the distribution, where
# the over/under lines sit. Out in the tail (35+ for a 22-point scorer at
# +1700) it is too wide, which turns a small disagreement into a huge fake
# edge. A price needs at least this model chance to count as a pick, which
# keeps picks to rungs near the range the model was checked on.
MIN_MODEL_P = 0.35
# A model far from the market is usually missing something (a new role, an
# injury), not finding free money, so a gap this big is excluded as a data
# problem, the same rule the MLB board uses.
MAX_DISAGREEMENT = 0.15


def is_pick(ev: float, model_p: float, market_p: float) -> bool:
    return (ev >= MIN_EV_TO_RECORD and model_p >= MIN_MODEL_P
            and abs(model_p - market_p) <= MAX_DISAGREEMENT)

COLUMNS = [
    "recorded_at", "game_date", "event_id", "commence_time", "home", "away",
    "player", "player_id", "threshold", "over_odds",
    "model_version", "model_mean", "model_p", "market_p", "pick_ev", "is_pick",
    "status", "actual", "result", "pnl_units",
]


def p_at_least(threshold: int, mean: float, dispersion: float | Callable) -> float:
    """Chance of scoring `threshold` points or more."""
    return float(negbin.over_prob(threshold - 0.5, mean, dispersion))


def fair_american(probability: float) -> int:
    """American odds at which a bet with this chance breaks even."""
    p = min(max(probability, _MIN_PROB), _MAX_PROB)
    return round(-100.0 * p / (1.0 - p)) if p >= 0.5 else round(100.0 * (1.0 - p) / p)


def player_means(ledger: pd.DataFrame, game_date: str, player: str) -> dict[str, float]:
    """Each model's projected points for a player on a date."""
    rows = ledger[(ledger["game_date"] == game_date) & (ledger["player"] == player)]
    return rows.drop_duplicates("model_version").set_index("model_version")["model_mean"].to_dict()


def ladder(means: dict[str, float], rungs: list[int] = RUNGS) -> pd.DataFrame:
    """Chance and fair odds of each X+ total, one column pair per model."""
    table = pd.DataFrame({"Points": [f"{rung}+" for rung in rungs]})
    for version in sorted(means):
        chances = [p_at_least(rung, means[version], DISPERSIONS[version]) for rung in rungs]
        table[f"{version} chance %"] = [c * 100.0 for c in chances]
        table[f"{version} fair odds"] = [fair_american(c) for c in chances]
    return table


def build_alt_rows(
    event: dict,
    lines: list[dict],
    predictions: dict[str, dict],
    recorded_at: str,
    game_date: str,
    *,
    model_version: str,
    dispersion: float | Callable,
) -> list[dict]:
    """One row per X+ price we can price. `lines` hold player, line (a half
    point such as 14.5, meaning 15+) and over_odds."""
    rows = []
    for item in lines:
        prediction = predictions.get(item["player"])
        point, odds = item["line"], item["over_odds"]
        if prediction is None or odds is None or float(point).is_integer():
            continue
        threshold = math.ceil(point)
        model_p = p_at_least(threshold, prediction["mean"], dispersion)
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
            "pick_ev": ev if picked else None,
            "is_pick": picked, "status": "pending",
        })
    return rows


def load_ledger(path: Path | None = None) -> pd.DataFrame:
    path = path or LEDGER_PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path)


def save_ledger(ledger: pd.DataFrame, path: Path | None = None) -> None:
    path = path or LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(path, index=False)


def append_rows(rows: list[dict], path: Path | None = None) -> int:
    """Add rows not already recorded for the same game, player, total and
    model. Returns how many were new."""
    path = path or LEDGER_PATH
    existing = load_ledger(path)
    seen = set(zip(existing["event_id"], existing["player"],
                   existing["threshold"], existing["model_version"]))
    fresh = []
    for row in rows:
        key = (row["event_id"], row["player"], row["threshold"], row["model_version"])
        if key not in seen:
            seen.add(key)
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


def record_event(event, lines, models, recorded_at: str, game_date: str,
                 path: Path | None = None) -> dict[str, int]:
    """Price one game's X+ lines with every model. One model failing never
    stops the others. Returns the new rows each model added."""
    names = [line["player"] for line in lines]
    added: dict[str, int] = {}
    for model in models:
        try:
            projections = model.project(event, names)
            rows = build_alt_rows(event, lines, projections, recorded_at, game_date,
                                  model_version=model.version, dispersion=model.dispersion)
            added[model.version] = append_rows(rows, path=path)
        except Exception:
            log.exception("model %s failed on X+ lines for %s @ %s",
                          model.version, event["away"], event["home"])
            added[model.version] = 0
    return added


def games_recorded(ledger: pd.DataFrame, game_date: str) -> int:
    """How many games on a date already have X+ prices recorded."""
    return int(ledger.loc[ledger["game_date"] == game_date, "event_id"].nunique())


def settle(ledger: pd.DataFrame, games: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """Grade finished games at a flat 1 unit; void players who never played.
    `games` needs player_id, game_date and pts."""
    out = ledger.astype({"result": object, "status": object}).copy()
    points = {
        (int(row.player_id), row.game_date.strftime("%Y-%m-%d")): float(row.pts)
        for row in games.itertuples()
    }
    for index in out.index[out["status"] == "pending"]:
        row = out.loc[index]
        key = (int(row["player_id"]), str(row["game_date"]))
        if key in points:
            actual = points[key]
            won = actual >= float(row["threshold"])
            out.loc[index, "status"] = "settled"
            out.loc[index, "actual"] = actual
            if row["is_pick"]:
                out.loc[index, "result"] = "win" if won else "loss"
                out.loc[index, "pnl_units"] = (
                    american_to_decimal(float(row["over_odds"])) - 1.0 if won else -1.0)
        elif str(row["game_date"]) < today.isoformat():
            out.loc[index, "status"] = "void"
            out.loc[index, "pnl_units"] = 0.0
    return out


def summary(ledger: pd.DataFrame, model_version: str | None = None) -> dict:
    picks = ledger[ledger["is_pick"].astype(bool)]
    if model_version is not None:
        picks = picks[picks["model_version"] == model_version]
    settled = picks[picks["status"] == "settled"]
    units = float(pd.to_numeric(settled["pnl_units"], errors="coerce").sum())
    return {
        "picks": len(picks), "settled": len(settled),
        "record": f"{(settled['result'] == 'win').sum()}-{(settled['result'] == 'loss').sum()}",
        "units": units,
        "roi_pct": units / len(settled) * 100.0 if len(settled) else 0.0,
    }


def suggestions(ledger: pd.DataFrame, game_date: str, top: int = 10) -> pd.DataFrame:
    """X+ bets worth a look on a date, best expected value first. Models
    that pick the same price are merged and counted in Agree."""
    day = ledger[(ledger["game_date"] == game_date) & ledger["is_pick"].astype(bool)]
    if day.empty:
        return pd.DataFrame()
    key = ["event_id", "player", "threshold"]
    agree = day.groupby(key)["model_version"].nunique().rename("Agree").reset_index()
    best = day.sort_values("pick_ev", ascending=False).drop_duplicates(key).merge(agree, on=key)
    # neighbouring rungs (14+, 15+, 16+) are one bet in practice: keep the best
    best = (best.sort_values(["Agree", "pick_ev"], ascending=False)
            .drop_duplicates(["event_id", "player"]).head(top))
    return pd.DataFrame({
        "Bet": best["player"] + " · " + best["threshold"].astype(int).astype(str) + "+ points",
        "Game": best["away"] + " @ " + best["home"],
        "Odds": best["over_odds"].to_numpy(),
        "Model projects": best["model_mean"].to_numpy(),
        "Model chance %": (best["model_p"] * 100.0).to_numpy(),
        "EV %": (best["pick_ev"] * 100.0).to_numpy(),
        "Agree": best["Agree"].to_numpy(),
    }).reset_index(drop=True)
