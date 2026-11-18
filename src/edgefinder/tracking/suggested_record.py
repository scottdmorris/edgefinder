"""Immutable offered slips and a frozen prospective experiment, stored transactionally.

Offers mean suggestions returned by the API, not clicks or real wagers. Repeated requests
for identical prices are deduplicated. Results are graded separately from the original quote.
"""
import datetime as dt
from contextlib import contextmanager
import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd

from ..betting.odds_math import american_to_decimal
from ..models import nba_stat_model
from . import settlement

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "suggested_slips.sqlite3"
EXPERIMENT = {"id": "higher-hit-v1", "model": "context-v2", "book": "fanduel",
              "style": "Higher hit rate", "legs": 2, "min_joint_probability": .60,
              "min_return": 1.30, "min_ev": .02, "min_history": 10,
              "max_minutes_cv": .25, "max_price_age_minutes": 90,
              "one_per_game": True, "first_qualifying_slip_per_day": True,
              "review_after_slips": 200, "review_after_game_days": 30,
              "success": "positive flat-unit return and Brier score below quoted market baseline",
              "min_leg_decimal": 1.10, "market_baseline": "1 / simulated product payout (margin included)",
              "fees": "before fees; simulated product payout, not a verified sportsbook parlay quote"}
# Many legs, one a night: Kalshi is the only source with enough worthwhile legs most nights.
# Last season's markets say it loses at real prices; this records whether it does here.
LONG_SHOT_EXPERIMENT = {"id": "long-shot-v1", "model": "context-v2", "book": "kalshi",
                        "style": "Long shot", "min_legs": 8, "max_legs": 10, "max_per_game": 2,
                        "min_leg_ev": .02, "first_qualifying_slip_per_day": True,
                        "review_after_game_days": 60,
                        "success": "positive flat-unit return over the review window",
                        "fees": "before Kalshi fees; product of the leg prices"}
EXPERIMENTS = {spec["id"]: spec for spec in (EXPERIMENT, LONG_SHOT_EXPERIMENT)}


@contextmanager
def connect(path: Path | None = None):
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS offers (id TEXT PRIMARY KEY, payload TEXT NOT NULL, result TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS experiment (trial TEXT, day TEXT, offer TEXT NOT NULL, PRIMARY KEY (trial,day))")
    db.execute("CREATE TABLE IF NOT EXISTS protocol (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    try:
        with db:
            yield db
    finally:
        db.close()


def freeze_protocol(db: sqlite3.Connection, spec: dict | None = None) -> None:
    """Reject new trial entries after a rule change; old results remain readable/gradable."""
    spec = spec or EXPERIMENT
    recipe_files = [Path(__file__).with_name("nba_parlay.py"),
                    Path(__file__).parents[1] / "models" / "recalibration.json",
                    Path(__file__).with_name("quote_evidence.py"),
                    Path(__file__).parents[1] / "api" / "suggestion_service.py",
                    Path(__file__).parents[1] / "api" / "service.py",
                    Path(__file__).parents[1] / "betting" / "correlated.py",
                    Path(__file__).parents[1] / "models" / "nba_recalibration.py"]
    hashes = {p.name: hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest() for p in recipe_files}
    protocol = json.dumps(spec | {"recipe_sha256": hashes}, sort_keys=True)
    db.execute("INSERT OR IGNORE INTO protocol VALUES (?, ?)", (spec["id"], protocol))
    stored = db.execute("SELECT payload FROM protocol WHERE id=?", (spec["id"],)).fetchone()[0]
    if stored != protocol:
        raise ValueError("Experiment rules changed: use a new experiment ID")


def _qualifies(payload: dict, spec: dict) -> bool:
    """The trial's own rules, checked again here so a caller cannot bypass the search."""
    legs = payload["legs"]
    if not (payload.get("model") == spec["model"] and payload.get("book") == spec["book"]
            and payload.get("style") == spec["style"] and not payload.get("game")
            and all(leg.get("evidence", {}).get("eligible") for leg in legs)):
        return False
    if spec is LONG_SHOT_EXPERIMENT:
        per_game = max((sum(leg["event_id"] == other["event_id"] for other in legs) for leg in legs), default=0)
        return (spec["min_legs"] <= len(legs) <= spec["max_legs"] and per_game <= spec["max_per_game"]
                and len({leg["player_id"] for leg in legs}) == len(legs))
    return (len(legs) == 2 and len({leg["event_id"] for leg in legs}) == 2
            and payload["probability"] >= .60 and payload["payout"] >= 1.30
            and payload["probability"] * payload["payout"] - 1 >= .02)


def archive(payload: dict, now: dt.datetime, path: Path | None = None,
            experiment: bool | str = False) -> str | None:
    """No retrospective offers. Original prices and probabilities cannot be overwritten.
    `experiment` is True for the higher-hit trial, or another trial's id."""
    if not payload["legs"] or any(pd.Timestamp(leg["tip"]) <= pd.Timestamp(now) for leg in payload["legs"]):
        return None
    spec = None
    if experiment:
        spec = EXPERIMENT if experiment is True else EXPERIMENTS[experiment]
        if not _qualifies(payload, spec):
            return None
    canonical = payload | {"legs": sorted(payload["legs"], key=lambda leg: json.dumps(leg, sort_keys=True))}
    identity = json.dumps(canonical, sort_keys=True, allow_nan=False)
    identifier = hashlib.sha256(identity.encode()).hexdigest()[:24]
    saved = json.dumps(payload | {"recorded_at": now.isoformat()}, sort_keys=True, allow_nan=False)
    with connect(path) as db:
        if spec:
            freeze_protocol(db, spec)
        db.execute("INSERT OR IGNORE INTO offers VALUES (?, ?, NULL)", (identifier, saved))
        if spec:
            db.execute("INSERT OR IGNORE INTO experiment VALUES (?, ?, ?)",
                       (spec["id"], payload["day"], identifier))
    return identifier


def grade(games: pd.DataFrame, today: dt.date, path: Path | None = None) -> int:
    complete = settlement.completed_games(games)
    results = {(int(r.player_id), pd.Timestamp(r.game_date).date().isoformat()): r
               for r in games.itertuples()}
    changed = 0
    with connect(path) as db:
        for identifier, raw in db.execute("SELECT id,payload FROM offers WHERE result IS NULL").fetchall():
            slip = json.loads(raw)
            statuses, remaining_payout = [], float(slip["payout"])
            for leg in slip["legs"]:
                box = results.get((leg["player_id"], slip["day"]))
                if box is None:
                    row = pd.Series({"game_date": slip["day"], "game": leg["game"]})
                    status = "void" if settlement.can_void(row, today, complete) else "pending"
                else:
                    value = getattr(box, nba_stat_model.STATS[leg["stat"]].column, None)
                    if value is None or pd.isna(value):
                        status = "pending"
                    elif value == leg["line"]:
                        status = "void"  # push: stake on this leg returned
                    else:
                        hit = value < leg["line"] if leg["side"] == "Under" else value > leg["line"]
                        status = "win" if hit else "loss"
                statuses.append(status)
                if status == "void":
                    remaining_payout /= american_to_decimal(leg["odds"])
            if "pending" in statuses:
                continue
            status = "void" if all(s == "void" for s in statuses) else "loss" if "loss" in statuses else "win"
            result = {"status": status, "units": 0 if status == "void" else -1 if status == "loss" else remaining_payout - 1,
                      "legs": statuses, "graded_at": today.isoformat(), "has_void": "void" in statuses}
            db.execute("UPDATE offers SET result=? WHERE id=? AND result IS NULL", (json.dumps(result), identifier))
            changed += 1
    return changed


def summary(path: Path | None = None) -> dict:
    if not (path or DB_PATH).exists():
        return {"offered": facts([]), "experiment": facts([]), "protocol": EXPERIMENT,
                "long_shot": facts([]), "long_shot_protocol": LONG_SHOT_EXPERIMENT}
    with connect(path) as db:
        rows = [(i, json.loads(p), json.loads(r) if r else None)
                for i, p, r in db.execute("SELECT id,payload,result FROM offers")]
        trial, trial_protocol = _trial(db, rows, EXPERIMENT)
        long_shot, long_shot_protocol = _trial(db, rows, LONG_SHOT_EXPERIMENT)
    return {"offered": facts(rows), "experiment": trial, "protocol": trial_protocol,
            "long_shot": long_shot, "long_shot_protocol": long_shot_protocol}


def _trial(db: sqlite3.Connection, rows: list, spec: dict) -> tuple[dict, dict]:
    selected = {r[0] for r in db.execute("SELECT offer FROM experiment WHERE trial=?", (spec["id"],))}
    stored = db.execute("SELECT payload FROM protocol WHERE id=?", (spec["id"],)).fetchone()
    return facts([r for r in rows if r[0] in selected]), json.loads(stored[0]) if stored else spec


def facts(rows: list) -> dict:
    graded = [(p, r) for _, p, r in rows if r and r["status"] != "void"]
    wins = sum(r["status"] == "win" for _, r in graded)
    units = sum(r["units"] for _, r in graded)
    # Voided legs change the wager: exclude those slips from probability calibration.
    clean = [(p, r) for p, r in graded if not r["has_void"]]
    def brier(key):
        return sum((p[key] - (r["status"] == "win")) ** 2 for p, r in clean) / len(clean) if clean else None
    return {"offered": len(rows), "graded": len(graded), "wins": wins, "losses": len(graded)-wins,
            "pending": sum(r is None for _, _, r in rows), "units": round(units, 3),
            "void": sum(bool(r and r["status"] == "void") for _, _, r in rows),
            "hit_pct": round(100*wins/len(graded), 1) if graded else None,
            "roi_pct": round(100*units/len(graded), 1) if graded else None,
            "brier": brier("probability"), "market_brier": brier("market_probability"),
            "calibration_n": len(clean), "game_days": len({p["day"] for p, _ in graded})}
