"""Paper-trade record: the app logs its own +EV picks (no money),
auto-settles them from final scores, and computes CLV against our
line-history archive. This builds the evidence for whether the model
actually beats FanDuel before real stakes ride on it.

Every pick is a flat 1-unit stake, the standard for judging a model.
"""

import datetime as dt
from pathlib import Path

import pandas as pd

from ..betting.odds_math import american_to_decimal, implied_prob
from ..data import line_history, mlb_api

PAPER_PATH = Path(__file__).resolve().parents[3] / "data" / "paper_log.csv"
MIN_EV_TO_RECORD = 0.02

COLUMNS = [
    "recorded_at", "game_date", "sport", "market", "side", "line",
    "home", "away", "commence_time", "description", "american_odds",
    "model_prob", "result", "pnl_units", "closing_odds", "clv_pct",
]

_MARKETS = (
    ("home_ml_ev", "ml", "home"),
    ("away_ml_ev", "ml", "away"),
    ("over_ev", "total", "over"),
    ("under_ev", "total", "under"),
)


def load_log() -> pd.DataFrame:
    if not PAPER_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PAPER_PATH)


def _save(df: pd.DataFrame) -> None:
    PAPER_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PAPER_PATH, index=False)


def record_board_picks(board: list[dict], game_date: str) -> int:
    """Record the best +EV side of each clean, upcoming game. Skips
    games already recorded for this date. Returns how many were added."""
    df = load_log()
    existing = set(zip(df["game_date"], df["description"]))
    added = []
    for game in board:
        if game.get("status") not in (None, "Preview") or game.get("suspect"):
            continue
        pick = _best_pick(game)
        if pick is None:
            continue
        if (game_date, pick["description"]) in existing:
            continue
        added.append({
            "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "game_date": game_date,
            "sport": "mlb",
            "result": "pending",
            "pnl_units": 0.0,
            "closing_odds": None,
            "clv_pct": None,
            "home": game["home"],
            "away": game["away"],
            "commence_time": game.get("game_time"),
            **pick,
        })
    if added:
        _save(pd.concat([df, pd.DataFrame(added)], ignore_index=True))
    return len(added)


def _best_pick(game: dict) -> dict | None:
    best = None
    for ev_key, market, side in _MARKETS:
        ev_value = game.get(ev_key)
        if ev_value is None or ev_value < MIN_EV_TO_RECORD:
            continue
        if best is None or ev_value > best[0]:
            best = (ev_value, market, side)
    if best is None:
        return None
    _, market, side = best
    if market == "ml":
        team = game[side]
        odds = game[f"{side}_ml"]
        prob = game[f"p_{side}_bet"]
        description = f"{team} ML ({game['away']} @ {game['home']})"
        line = None
    else:
        line = game["total_line"]
        odds = game[f"{side}_odds"]
        prob = game[f"p_{side}_bet"]
        description = (f"{side.capitalize()} {line} "
                       f"({game['away']} @ {game['home']})")
    return {
        "market": market, "side": side, "line": line,
        "description": description, "american_odds": odds,
        "model_prob": prob,
    }


def grade_pick(row: dict, home_score: int, away_score: int) -> tuple[str, float]:
    """Pure settlement logic: (result, pnl_units) for a 1-unit stake."""
    if row["market"] == "ml":
        winner = "home" if home_score > away_score else "away"
        won = row["side"] == winner
    else:
        total = home_score + away_score
        line = float(row["line"])
        if total == line:
            return "push", 0.0
        went_over = total > line
        won = (row["side"] == "over") == went_over
    if won:
        return "win", american_to_decimal(float(row["american_odds"])) - 1.0
    return "loss", -1.0


def settle_pending(season: int) -> int:
    """Settle pending picks against final scores; attach CLV from the
    line-history archive where a pre-game snapshot exists."""
    df = load_log()
    pending = df[df["result"] == "pending"]
    if pending.empty:
        return 0
    results = {
        (g["date"], g["home"], g["away"]): g
        for g in mlb_api.season_results(season)
    }
    settled = 0
    for index, row in pending.iterrows():
        game = results.get((row["game_date"], row["home"], row["away"]))
        if game is None:
            continue
        result, pnl = grade_pick(row.to_dict(), game["home_score"],
                                 game["away_score"])
        df.loc[index, "result"] = result
        df.loc[index, "pnl_units"] = round(pnl, 3)
        closing = _closing_odds_for(row)
        if closing is not None:
            df.loc[index, "closing_odds"] = closing
            placed = implied_prob(float(row["american_odds"]))
            closed = implied_prob(closing)
            df.loc[index, "clv_pct"] = round(
                (closed - placed) / placed * 100.0, 2)
        settled += 1
    if settled:
        _save(df)
    return settled


def _closing_odds_for(row: pd.Series) -> float | None:
    snapshot = line_history.closing_snapshot(
        row["home"], row["away"], row.get("commence_time"))
    if snapshot is None:
        return None
    field = {
        ("ml", "home"): "home_ml", ("ml", "away"): "away_ml",
        ("total", "over"): "over_odds", ("total", "under"): "under_odds",
    }[(row["market"], row["side"])]
    value = snapshot.get(field)
    return None if value is None or pd.isna(value) else float(value)


def summary(df: pd.DataFrame) -> dict:
    settled = df[df["result"].isin(["win", "loss", "push"])]
    pnl = settled["pnl_units"].sum()
    graded = settled[settled["result"] != "push"]
    clv = pd.to_numeric(df["clv_pct"], errors="coerce").dropna()
    return {
        "picks": len(df),
        "settled": len(settled),
        "record": f"{(graded['result'] == 'win').sum()}-{(graded['result'] == 'loss').sum()}",
        "units": round(float(pnl), 2),
        "roi_pct": round(float(pnl / len(settled) * 100.0), 1) if len(settled) else 0.0,
        "avg_clv_pct": round(float(clv.mean()), 2) if len(clv) else None,
    }
