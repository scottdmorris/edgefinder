"""The public record: every pick as it was locked, and how it turned out.

The record is worth something only because of one rule: a pick is written
down before the game and only its result is filled in afterwards. This
module doesn't ask anyone to take that on trust. It measures it, counting
how many picks were recorded after tip-off (there should be none) and
showing when each was locked.

Pure shaping with no web framework in it.
"""

import pandas as pd

from ..models import nba_stat_model
from .nba_paper import DEFAULT_STAT

EASTERN = "America/New_York"
MIN_LINES_FOR_VERDICT = 300     # a few weeks of games; fewer settled lines than this is noise
CALIBRATION_EDGES = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]


def _picks(ledger: pd.DataFrame) -> pd.DataFrame:
    return ledger[ledger["pick_side"].notna()]


def locked_picks(ledger: pd.DataFrame) -> pd.DataFrame:
    """Every pick with when it was locked and how long before tip-off, newest
    first. `Result` is empty until the game is graded."""
    picks = _picks(ledger).copy()
    if picks.empty:
        return pd.DataFrame(columns=[
            "Game day", "Player", "Bet", "Odds", "Model", "Locked", "Min before tip",
            "Status", "Result", "Units", "model_version", "stat"])
    recorded = pd.to_datetime(picks["recorded_at"], utc=True, format="ISO8601")
    tip = pd.to_datetime(picks["commence_time"], utc=True, format="ISO8601")
    stats = picks["stat"].fillna(DEFAULT_STAT)
    words = stats.map(lambda s: nba_stat_model.STATS[s].label.lower())
    table = pd.DataFrame({
        "Game day": picks["game_date"].to_numpy(),
        "Player": picks["player"].to_numpy(),
        "Bet": (picks["pick_side"].str.capitalize() + " " + picks["line"].map("{:g}".format)
                + " " + words).to_numpy(),
        "Odds": picks["pick_odds"].to_numpy(),
        "Model": picks["model_version"].to_numpy(),
        "Locked": recorded.dt.tz_convert(EASTERN).to_numpy(),
        "Min before tip": ((tip - recorded).dt.total_seconds() / 60.0).to_numpy(),
        "Status": picks["status"].to_numpy(),
        "Result": picks["result"].fillna("").to_numpy(),
        "Units": pd.to_numeric(picks["pnl_units"], errors="coerce").to_numpy(),
        "model_version": picks["model_version"].to_numpy(), "stat": stats.to_numpy(),
    })
    return table.sort_values("Locked", ascending=False).reset_index(drop=True)


def integrity(ledger: pd.DataFrame) -> dict:
    """Facts about the rule, not claims: how many picks, how many were graded,
    how many were recorded at or after tip-off, and the first and last lock."""
    locked = locked_picks(ledger)
    if locked.empty:
        return {"picks": 0, "graded": 0, "after_tip": 0, "first_lock": None, "last_lock": None}
    return {
        "picks": len(locked),
        "graded": int(locked["Status"].isin(["settled", "void"]).sum()),
        "after_tip": int((locked["Min before tip"] <= 0).sum()),
        "first_lock": locked["Locked"].min(), "last_lock": locked["Locked"].max(),
    }


def lead_label(minutes: float) -> str:
    """'7 h 5 min before tip', or 'after tip-off' when a pick was recorded too late."""
    if minutes <= 0:
        return "AFTER TIP-OFF"
    hours, rest = divmod(int(minutes), 60)
    return f"{hours} h {rest} min before tip" if hours else f"{rest} min before tip"


def graded(locked: pd.DataFrame) -> pd.DataFrame:
    """Picks that have a result, in the order their games were played."""
    return locked[locked["Result"].isin(["win", "loss"])].sort_values("Game day")


def daily_results(locked: pd.DataFrame) -> pd.DataFrame:
    """Per game day and model: picks made, picks graded, record and units."""
    if locked.empty:
        return pd.DataFrame(columns=["Game day", "Model", "Picks", "Graded", "Record", "Units"])
    rows = []
    for (day, model), group in locked.groupby(["Game day", "Model"]):
        done = group[group["Result"].isin(["win", "loss"])]
        rows.append({
            "Game day": day, "Model": model, "Picks": len(group), "Graded": len(done),
            "Record": f"{(done['Result'] == 'win').sum()}-{(done['Result'] == 'loss').sum()}",
            "Units": float(done["Units"].sum()),
        })
    return pd.DataFrame(rows).sort_values(["Game day", "Model"], ascending=[False, True]) \
        .reset_index(drop=True)


def cumulative_units(locked: pd.DataFrame) -> pd.DataFrame:
    """Running profit in units, per model, by game day, over graded picks."""
    done = graded(locked)
    if done.empty:
        return pd.DataFrame(columns=["Game day", "Model", "Units"])
    by_day = done.groupby(["Model", "Game day"])["Units"].sum().reset_index()
    by_day["Units"] = by_day.groupby("Model")["Units"].cumsum()
    return by_day[["Game day", "Model", "Units"]]


def calibration_bins(ledger: pd.DataFrame, model_version: str) -> pd.DataFrame:
    """Does a 70% prediction come true about 70% of the time? Graded lines are
    grouped by the model's chance of the over; each group shows the model's
    average chance, the market's, and how often the over really happened."""
    settled = ledger[(ledger["model_version"] == model_version)
                     & (ledger["status"] == "settled")].dropna(subset=["went_over"])
    columns = ["Model chance", "Lines", "Model said", "Market said", "Actually happened"]
    if settled.empty:
        return pd.DataFrame(columns=columns)
    p = settled["model_p_over"].astype(float)
    bins = pd.cut(p, CALIBRATION_EDGES, include_lowest=True)
    rows = []
    for interval, group in settled.groupby(bins, observed=True):
        rows.append({
            "Model chance": f"{max(interval.left, 0.0) * 100:.0f}-{interval.right * 100:.0f}%",
            "Lines": len(group),
            "Model said": float(group["model_p_over"].astype(float).mean()) * 100.0,
            "Market said": float(group["fair_p_over"].astype(float).mean()) * 100.0,
            "Actually happened": float(group["went_over"].astype(float).mean()) * 100.0,
        })
    return pd.DataFrame(rows, columns=columns)


def verdict(brier_model: float | None, brier_market: float | None, lines: int,
            minimum: int = MIN_LINES_FOR_VERDICT) -> str:
    """One honest sentence on whether the model beats the market so far."""
    if lines == 0 or brier_model is None or brier_market is None:
        return "No results yet. The first games are graded the morning after they're played."
    if lines < minimum:
        return (f"{lines} lines graded so far. That's too few to say anything: "
                f"it takes about {minimum} before the comparison means much.")
    gap = brier_market - brier_model
    if abs(gap) < 0.002:
        return "Level with the market so far: no real difference between the two."
    if gap > 0:
        return (f"Ahead of the market so far, by {gap:.4f} on accuracy (lower scores are "
                "better). Still needs to hold up over more games before it means much.")
    return (f"Behind the market so far, by {-gap:.4f} on accuracy (lower scores are better). "
            "Right now the sportsbook's own odds are the better guide.")


def clv_summary(ledger: pd.DataFrame) -> dict[str, dict]:
    """Closing-line value of the picks, per price source: {book: {"picks", "measured",
    "avg_clv_pct", "beat_close_pct"}}. CLV asks whether the market later moved our way, which
    needs far fewer picks to read than wins and losses do. `measured` counts picks that have
    a closing price to compare with."""
    picks = ledger[ledger["pick_side"].notna()]
    out = {}
    for book, group in picks.groupby(picks["book"].fillna("fanduel")):
        clv = pd.to_numeric(group["clv_pct"], errors="coerce").dropna()
        out[book] = {
            "picks": len(group), "measured": len(clv),
            "avg_clv_pct": float(clv.mean()) if len(clv) else None,
            "beat_close_pct": float((clv > 0).mean() * 100.0) if len(clv) else None}
    return out
