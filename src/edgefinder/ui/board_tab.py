"""Today's Board: model predictions vs FanDuel lines, ranked by EV."""

import datetime as dt

import pandas as pd
import streamlit as st

from ..data import line_history, odds_api
from . import shared


def render() -> None:
    st.subheader("Today's MLB Board")
    season, today_iso = shared.current_season_and_date()
    date_picked = st.date_input("Slate date", dt.date.fromisoformat(today_iso))
    if not odds_api.get_api_key():
        st.info(
            "No Odds API key configured — showing model predictions only. "
            "Add a free key (the-odds-api.com) to `data/odds_api_key.txt` "
            "to pull live FanDuel lines, or evaluate odds manually in the "
            "**Bet Evaluator** tab."
        )
    try:
        board = shared.cached_board(season, date_picked.isoformat())
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return
    if not board:
        st.warning("No games scheduled for this date.")
        return
    st.caption(
        f"{len(board)} games · Elo + probable-pitcher model · "
        "fair odds are the model's no-vig price"
    )
    st.dataframe(_to_display(board), use_container_width=True, hide_index=True)
    st.caption(
        "EV columns appear when live FanDuel odds are available. A bet is "
        "only worth considering when its EV is positive after vig. "
        "⚠️ marks games where model and market disagree implausibly — "
        "that's a data problem or scratched starter, not free money; "
        "those games are excluded from parlay suggestions. "
        "**Sharp edge** = best EV betting FanDuel's price against "
        "Pinnacle's devigged probability — the most trustworthy edge "
        "signal on the board (it needs no model at all)."
    )
    _line_movement(board)


def _line_movement(board: list[dict]) -> None:
    with st.expander("📉 Line movement"):
        labels = [f"{g['away']} @ {g['home']}" for g in board]
        choice = st.selectbox("Game", labels, key="line_move_game")
        game = board[labels.index(choice)]
        history = line_history.history_for(game["home"], game["away"],
                                           game.get("game_time"))
        if history.empty:
            st.info(
                "No snapshots archived for this game yet. Every odds "
                "refresh records one, so history builds as you use the app."
            )
            return
        st.dataframe(
            history[["fetched_at", "home_ml", "away_ml", "total_line",
                     "over_odds", "under_odds"]],
            use_container_width=True, hide_index=True,
        )


def _to_display(board: list[dict]) -> pd.DataFrame:
    rows = []
    for g in board:
        flag = "⚠️ " if g.get("suspect") else ""
        row = {
            "Matchup": f"{flag}{g['away']} @ {g['home']}",
            "Pitchers": _pitchers(g),
            "Home win %": shared.fmt_pct(g["p_home"]),
            "Fair home ML": shared.fair_american(g["p_home"]),
            "Fair away ML": shared.fair_american(g["p_away"]),
            "Model total": None if g["model_total"] is None else round(g["model_total"], 1),
        }
        if g.get("home_ml") is not None:
            row["FD home ML"] = shared.fmt_american(g.get("home_ml"))
            row["FD away ML"] = shared.fmt_american(g.get("away_ml"))
            row["Home ML EV"] = shared.fmt_pct(g.get("home_ml_ev"))
            row["Away ML EV"] = shared.fmt_pct(g.get("away_ml_ev"))
        if g.get("sharp_best_ev") is not None:
            row["Sharp edge"] = shared.fmt_pct(g.get("sharp_best_ev"))
        if g.get("total_line") is not None:
            row["FD total"] = g.get("total_line")
            row["Over EV"] = shared.fmt_pct(g.get("over_ev"))
            row["Under EV"] = shared.fmt_pct(g.get("under_ev"))
        rows.append(row)
    return pd.DataFrame(rows)


def _pitchers(g: dict) -> str:
    away = g.get("away_pitcher") or "TBD"
    home = g.get("home_pitcher") or "TBD"
    away_era = f" ({g['away_era']:.2f})" if g.get("away_era") else ""
    home_era = f" ({g['home_era']:.2f})" if g.get("home_era") else ""
    return f"{away}{away_era} vs {home}{home_era}"
