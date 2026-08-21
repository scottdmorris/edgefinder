"""CSV-backed bet log with P/L and closing-line-value tracking.

CLV (did you beat the closing line?) is the strongest evidence of a
real edge -- long before win/loss records are statistically meaningful.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from ..betting.odds_math import american_to_decimal, implied_prob

LOG_PATH = Path(__file__).resolve().parents[3] / "data" / "bet_log.csv"

COLUMNS = [
    "placed_on", "sport", "bet_type", "description", "american_odds",
    "stake", "model_prob", "result", "pnl", "closing_odds", "clv_pct",
]
RESULT_CHOICES = ("pending", "win", "loss", "push")


def load_log() -> pd.DataFrame:
    if not LOG_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(LOG_PATH)


def _save(df: pd.DataFrame) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(LOG_PATH, index=False)


def add_bet(
    sport: str,
    bet_type: str,
    description: str,
    american_odds: float,
    stake: float,
    model_prob: float,
) -> pd.DataFrame:
    df = load_log()
    row = {
        "placed_on": date.today().isoformat(),
        "sport": sport,
        "bet_type": bet_type,
        "description": description,
        "american_odds": american_odds,
        "stake": stake,
        "model_prob": model_prob,
        "result": "pending",
        "pnl": 0.0,
        "closing_odds": None,
        "clv_pct": None,
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save(df)
    return df


def settle_bet(
    index: int,
    result: str,
    closing_odds: float | None = None,
) -> pd.DataFrame:
    if result not in RESULT_CHOICES:
        raise ValueError(f"result must be one of {RESULT_CHOICES}")
    df = load_log().copy()
    if index not in df.index:
        raise IndexError(f"No bet at index {index}")
    row = df.loc[index]
    stake = float(row["stake"])
    odds = float(row["american_odds"])
    pnl = {
        "win": stake * (american_to_decimal(odds) - 1.0),
        "loss": -stake,
        "push": 0.0,
        "pending": 0.0,
    }[result]
    df.loc[index, "result"] = result
    df.loc[index, "pnl"] = round(pnl, 2)
    if closing_odds is not None:
        df.loc[index, "closing_odds"] = closing_odds
        placed = implied_prob(odds)
        closed = implied_prob(closing_odds)
        df.loc[index, "clv_pct"] = round((closed - placed) / placed * 100.0, 2)
    _save(df)
    return df


def summary(df: pd.DataFrame) -> dict:
    settled = df[df["result"].isin(["win", "loss", "push"])]
    staked = settled["stake"].sum()
    pnl = settled["pnl"].sum()
    clv = pd.to_numeric(df["clv_pct"], errors="coerce").dropna()
    return {
        "bets_placed": len(df),
        "bets_settled": len(settled),
        "total_staked": round(float(staked), 2),
        "net_pnl": round(float(pnl), 2),
        "roi_pct": round(float(pnl / staked * 100.0), 2) if staked else 0.0,
        "avg_clv_pct": round(float(clv.mean()), 2) if len(clv) else None,
    }
