"""Soccer board: three-way (win/draw/win) and totals EV per league."""

import pandas as pd
import streamlit as st

from .. import pipeline_soccer
from ..data import odds_api
from . import shared


@st.cache_data(ttl=900, show_spinner="Fitting league model...")
def _cached_board(league: str):
    return pipeline_soccer.build_soccer_board(league)


def render() -> None:
    st.subheader("Soccer")
    league = st.selectbox("League", list(odds_api.SOCCER_LEAGUES))
    if not odds_api.get_api_key():
        st.info("Add an Odds API key to pull FanDuel soccer lines.")
        return
    try:
        board, matches_trained = _cached_board(league)
    except Exception as exc:
        st.error(f"Could not build the {league} board: {exc}")
        return
    if not board:
        st.info(
            f"No upcoming {league} matches with FanDuel lines right now. "
            "European seasons run August-May; check back near matchdays."
        )
        return
    st.caption(
        f"{len(board)} matches · Poisson attack/defense model trained on "
        f"{matches_trained} league results · EV is market-anchored "
        "(30% model / 70% devigged FanDuel price)"
    )
    st.dataframe(_to_display(board), use_container_width=True, hide_index=True)
    st.caption(
        "Draws are a real outcome — a 'sure win' home side still loses "
        "the bet in a draw, which is why home/away EVs look thinner "
        "than the probabilities suggest. ⚠️ = implausible model-market "
        "gap (promoted team, missing data): don't bet those."
    )


def _to_display(board: list[dict]) -> pd.DataFrame:
    rows = []
    for m in board:
        flag = "⚠️ " if m.get("suspect") else ""
        rows.append({
            "Match": f"{flag}{m['home']} v {m['away']}",
            "Kickoff (UTC)": m.get("commence_time"),
            "Home %": shared.fmt_pct(m["p_home"]),
            "Draw %": shared.fmt_pct(m["p_draw"]),
            "Away %": shared.fmt_pct(m["p_away"]),
            "FD H/D/A": (f"{shared.fmt_american(m.get('home_ml'))} / "
                         f"{shared.fmt_american(m.get('draw_ml'))} / "
                         f"{shared.fmt_american(m.get('away_ml'))}"),
            "Home EV": shared.fmt_pct(m.get("home_ev")),
            "Draw EV": shared.fmt_pct(m.get("draw_ev")),
            "Away EV": shared.fmt_pct(m.get("away_ev")),
            "Goals line": m.get("total_line"),
            "Over EV": shared.fmt_pct(m.get("over_ev")),
            "Under EV": shared.fmt_pct(m.get("under_ev")),
        })
    return pd.DataFrame(rows)
