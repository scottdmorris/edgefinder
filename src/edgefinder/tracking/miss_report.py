"""What the misses say: where each model's FanDuel points picks lose, and how much of its
disagreement with the line has come true across every settled line.

Read-only and for the settle log. Nothing here feeds back into the models: the record has
to stay an honest test, so a lesson from it becomes a new model version, not a quiet tweak.
"""

import math

import pandas as pd

from .nba_paper import DEFAULT_BOOK, DEFAULT_STAT

MIN_LINES = 30                  # fewer settled lines than this cannot say anything
Z_95 = 1.96
PRICE_BANDS = (("-130 or shorter", lambda o: o <= -130),
               ("-129 to -101", lambda o: (o > -130) & (o < -100)),
               ("even or plus money", lambda o: (o == -100) | (o >= 100)))


def _settled(ledger: pd.DataFrame, version: str) -> pd.DataFrame:
    rows = ledger[(ledger["model_version"] == version) & (ledger["status"] == "settled")
                  & (ledger["stat"].fillna(DEFAULT_STAT) == DEFAULT_STAT)
                  & (ledger["book"].fillna(DEFAULT_BOOK) == DEFAULT_BOOK)]
    return rows.assign(actual=pd.to_numeric(rows["actual"], errors="coerce"),
                       model_mean=pd.to_numeric(rows["model_mean"], errors="coerce"),
                       pick_odds=pd.to_numeric(rows["pick_odds"], errors="coerce"),
                       pnl_units=pd.to_numeric(rows["pnl_units"], errors="coerce"))


def _picks(ledger: pd.DataFrame, version: str) -> pd.DataFrame:
    rows = _settled(ledger, version)
    return rows[rows["pick_side"].notna()]


def _facts(picks: pd.DataFrame) -> dict:
    """How a group of picks did, and how far the result landed from the projection."""
    return {"n": len(picks),
            "win_pct": round(float((picks["result"] == "win").mean()) * 100, 1),
            "units": round(float(picks["pnl_units"].sum()), 2),
            "miss": round(float((picks["actual"] - picks["model_mean"]).mean()), 2)}


def side_split(ledger: pd.DataFrame, version: str) -> dict[str, dict]:
    picks = _picks(ledger, version)
    return {side: _facts(group) for side, group in picks.groupby("pick_side")}


def price_split(ledger: pd.DataFrame, version: str) -> dict[str, dict]:
    picks = _picks(ledger, version)
    split = {label: picks[inside(picks["pick_odds"])] for label, inside in PRICE_BANDS}
    return {label: _facts(group) for label, group in split.items() if not group.empty}


def disagreement_share(ledger: pd.DataFrame, version: str) -> dict | None:
    """Fit actual - line = share * (projection - line) on every settled line the model
    priced. 1 means the model's disagreement with the line came true in full, 0 that the
    line already knew everything. None until there are MIN_LINES lines."""
    rows = _settled(ledger, version).dropna(subset=["actual", "model_mean"]) \
        .drop_duplicates(["event_id", "player"])
    if len(rows) < MIN_LINES:
        return None
    x = (rows["model_mean"] - rows["line"]).to_numpy(float)
    y = (rows["actual"] - rows["line"]).to_numpy(float)
    spread = float((x * x).sum())
    if spread == 0:
        return None
    share = float((x * y).sum() / spread)
    residual = float(((y - share * x) ** 2).sum()) / (len(rows) - 1)
    return {"n": len(rows), "share": share,
            "plus_minus": Z_95 * math.sqrt(residual / spread)}


def _group_text(label: str, facts: dict) -> str:
    return (f"{label} {facts['n']} picks {facts['win_pct']:.1f}% {facts['units']:+.2f}u, "
            f"scored {facts['miss']:+.1f} vs projection")


def report_lines(ledger: pd.DataFrame) -> list[str]:
    """The settle log's section, one block per model with settled points picks."""
    if ledger.empty:
        return []
    versions = [v for v in sorted(ledger["model_version"].dropna().unique())
                if not _picks(ledger, v).empty]
    if not versions:
        return []
    lines = ["", "What the misses say (FanDuel points; a lesson here becomes a new model "
                 "version, never a change to these):"]
    for version in versions:
        sides = side_split(ledger, version)
        lines.append(f"[{version}] " + "; ".join(_group_text(s, f) for s, f in sides.items()))
        prices = price_split(ledger, version)
        lines.append("  by price: " + "; ".join(
            f"{label} {f['n']} picks {f['win_pct']:.1f}% {f['units']:+.2f}u"
            for label, f in prices.items()))
        share = disagreement_share(ledger, version)
        lines.append("  " + ("too few settled lines to judge its disagreement with the line"
                             if share is None else
                             f"{share['share']:.0%} ± {share['plus_minus']:.0%} of its "
                             f"disagreement with the line came true ({share['n']} lines)"))
    return lines
