"""Recorded prices and player-history checks; no requests or fitted confidence claims."""
import math

import pandas as pd

from ..betting.odds_math import american_to_decimal
from ..models import nba_stat_model

MAX_PRICE_AGE_MINUTES = 90
MIN_HISTORY = 10
MAX_MINUTES_CV = .25


def assess(row: pd.Series | dict, games: pd.DataFrame, recorded_at, now) -> dict:
    """History always ends before the game day; displayed ranges are historical, not forecasts."""
    now = pd.Timestamp(now)
    stamp = pd.to_datetime(recorded_at, utc=True, errors="coerce")
    age = (now - stamp).total_seconds() / 60 if pd.notna(stamp) else None
    warnings = []
    if age is None or age < 0 or age > MAX_PRICE_AGE_MINUTES:
        warnings.append("Price not checked in the last 90 minutes")
    before = games
    if not games.empty:
        before = games[(games.player_id == int(row["player_id"]))
                       & (games.game_date < pd.Timestamp(row["date"]))].sort_values("game_date").tail(20)
    count = len(before)
    if count < MIN_HISTORY:
        warnings.append("Fewer than 10 prior games")
    cv = None
    if count and "minutes" in before:
        minutes = pd.to_numeric(before.minutes.tail(10), errors="coerce").dropna()
        if len(minutes) < MIN_HISTORY:
            warnings.append("Fewer than 10 valid minutes observations")
        mean = float(minutes.mean())
        cv = float(minutes.std(ddof=0) / mean) if mean > 0 else None
        if cv is None or not math.isfinite(cv) or cv > MAX_MINUTES_CV:
            warnings.append("Minutes have been unstable")
        if mean > 0 and abs(float(minutes.tail(3).mean()) / mean - 1) > .25:
            warnings.append("Recent playing time has changed")
    elif count:
        warnings.append("Minutes history unavailable")
    if count and (pd.Timestamp(row["date"]) - before.game_date.max()).days > 7:
        warnings.append("Returning after more than a week without a game")
    if count and "team" in before and before.team.tail(10).nunique() > 1:
        warnings.append("Recent team change; role may differ")
    hit_rate, low, high = None, None, None
    column = nba_stat_model.STATS[row["stat_key"]].column
    if count and column in before:
        values = pd.to_numeric(before[column], errors="coerce").dropna()
        hits = values > float(row["line"]) if row["Side"] != "Under" else values < float(row["line"])
        if len(values):
            hit_rate = round(float(hits.mean()) * 100, 1)
            low, high = [round(float(v), 1) for v in values.quantile([.1, .9])]
    if hit_rate is None:
        warnings.append("Stat history unavailable")
    return {"eligible": not warnings, "warnings": warnings, "history_games": count,
            "recent_hit_pct": hit_rate, "historical_low": low, "historical_high": high,
            "minutes_cv": round(cv, 3) if cv is not None and math.isfinite(cv) else None,
            "price_at": stamp.isoformat() if pd.notna(stamp) else None,
            "price_age_minutes": round(age, 1) if age is not None else None,
            "injuries": "Injury status is not verified by these history checks"}


def comparisons(row: pd.Series, snapshots: pd.DataFrame, now, tip) -> list[dict]:
    """Both prices, including different lines; only equal lines get a better-price label."""
    if snapshots.empty or row["stat_key"] != "points":
        return []
    mine = snapshots[(snapshots.event_id.astype(str) == str(row["event_id"]))
                     & (snapshots.player == row["Player"])].copy()
    fetched = pd.to_datetime(mine.fetched_at, utc=True, errors="coerce")
    cutoff = min(pd.Timestamp(now), pd.Timestamp(tip))
    mine = mine[(fetched <= cutoff) & (fetched < pd.Timestamp(tip))]
    if mine.empty:
        return []
    latest = mine.sort_values("fetched_at").iloc[-1]
    side = "under_odds" if row["Side"] == "Under" else "over_odds"
    if pd.isna(latest[side]):
        return []
    same = float(latest.line) == float(row["line"])
    age = (pd.Timestamp(now) - pd.Timestamp(latest.fetched_at)).total_seconds() / 60
    return [{"book": "DraftKings", "line": float(latest.line), "odds": int(latest[side]),
             "fetched_at": latest.fetched_at, "stale": age > MAX_PRICE_AGE_MINUTES,
             "same_line": same,
             "better_payout": same and age <= MAX_PRICE_AGE_MINUTES
             and american_to_decimal(latest[side]) > american_to_decimal(row["Odds"])}]
