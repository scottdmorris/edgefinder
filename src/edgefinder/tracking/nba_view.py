"""Shapes the NBA paper ledger and snapshot archive into display tables.

Pure data shaping with no Streamlit in it, so the dashboard tab stays thin
and this is testable.
"""

import pandas as pd

from . import nba_paper

KEY = ["event_id", "player", "line"]


def game_dates(ledger: pd.DataFrame) -> list[str]:
    """Dates that have recorded lines, newest first."""
    return sorted(ledger["game_date"].dropna().unique(), reverse=True)


def lines_for_date(ledger: pd.DataFrame, game_date: str) -> pd.DataFrame:
    """One row per line on a date, with every model's projection,
    probability and pick side by side next to the market's own devigged
    probability. Gap is the newest model's projection minus the line."""
    day = ledger[ledger["game_date"] == game_date]
    if day.empty:
        return pd.DataFrame()
    versions = sorted(day["model_version"].dropna().unique())
    table = day.drop_duplicates(KEY)[
        KEY + ["home", "away", "over_odds", "under_odds", "fair_p_over"]]
    for version in versions:
        part = day[day["model_version"] == version][
            KEY + ["model_mean", "model_p_over", "pick_side"]].rename(columns={
                "model_mean": f"{version} proj",
                "model_p_over": f"{version} P(over)",
                "pick_side": f"{version} pick",
            })
        table = table.merge(part, on=KEY, how="left")

    projections = [f"{version} proj" for version in versions]
    newest_first = table[projections[::-1]].bfill(axis=1).iloc[:, 0]
    table = table.assign(
        Game=table["away"] + " @ " + table["home"],
        Gap=newest_first - table["line"],
    )
    for version in versions:
        table[f"{version} pick"] = table[f"{version} pick"].fillna("")

    # the columns you read first (what sorts the table) go left; odds go last
    columns = ["Game", "player", "line", "Gap", "fair_p_over"]
    for version in versions:
        columns += [f"{version} proj", f"{version} P(over)", f"{version} pick"]
    table = table[columns + ["over_odds", "under_odds"]].rename(columns={
        "player": "Player", "line": "Line", "over_odds": "Over odds",
        "under_odds": "Under odds", "fair_p_over": "Market P(over)",
    })
    return table.sort_values(["Game", "Player"]).reset_index(drop=True)


def suggestions(ledger: pd.DataFrame, game_date: str, top: int = 10) -> pd.DataFrame:
    """The paper bets worth looking at on a date: lines where a model sees
    positive expected value, best first. Models that pick the same side of
    the same line are merged into one row and counted in Agree."""
    day = ledger[(ledger["game_date"] == game_date) & ledger["pick_side"].notna()
                 & (ledger["pick_side"] != "")]
    if day.empty:
        return pd.DataFrame()
    agree = day.groupby(KEY + ["pick_side"])["model_version"].nunique().rename("Agree")
    best = day.sort_values("pick_ev", ascending=False).drop_duplicates(KEY + ["pick_side"])
    best = best.merge(agree.reset_index(), on=KEY + ["pick_side"])
    best = best.sort_values(["Agree", "pick_ev"], ascending=False).head(top)
    return pd.DataFrame({
        "player_id": best["player_id"].astype(int).to_numpy(),
        "Bet": best["player"] + " · " + best["pick_side"].str.capitalize() + " "
               + best["line"].astype(str) + " points",
        "Game": best["away"] + " @ " + best["home"],
        "Odds": best["pick_odds"].to_numpy(),
        "Model projects": best["model_mean"].to_numpy(),
        "EV %": (best["pick_ev"] * 100.0).to_numpy(),
        "Agree": best["Agree"].to_numpy(),
    }).reset_index(drop=True)


def scorecard(ledger: pd.DataFrame) -> pd.DataFrame:
    """Per-model results: pick record and closing-line value, plus the
    Brier scores of the model and the market on every settled line."""
    rows = {}
    for version in sorted(ledger["model_version"].dropna().unique()):
        picks = nba_paper.summary(ledger, model_version=version)
        calibration = nba_paper.calibration_summary(ledger, model_version=version)
        rows[version] = {
            "Picks settled": picks["settled"],
            "Record": picks["record"],
            "Units": picks["units"],
            "ROI %": picks["roi_pct"],
            "Avg CLV %": picks["avg_clv_pct"],
            "Lines scored": calibration["n"],
            "Model Brier": calibration["brier_model"],
            "Market Brier": calibration["brier_market"],
        }
    return pd.DataFrame(rows).T


def collection_status(snapshots: pd.DataFrame, ledger: pd.DataFrame) -> dict:
    """How much the scheduled jobs have collected so far."""
    return {
        "games": int(snapshots["event_id"].nunique()),
        "lines_archived": len(snapshots),
        "last_snapshot": None if snapshots.empty else str(snapshots["fetched_at"].max()),
        "ledger_rows": len(ledger),
        "settled": int((ledger["status"] == "settled").sum()),
    }
