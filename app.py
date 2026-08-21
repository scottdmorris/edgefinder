"""EdgeFinder: MLB/NBA betting-value dashboard for FanDuel.

Run with:  .venv\\Scripts\\streamlit run app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from edgefinder import config
from edgefinder.data import odds_api
from edgefinder.ui import (
    betlog_tab, board_tab, evaluator_tab, parlay_tab, soccer_tab, ufc_tab,
)

st.set_page_config(page_title="EdgeFinder", page_icon="📈", layout="wide")


def render_sidebar() -> dict:
    settings = config.load_settings()
    st.sidebar.title("📈 EdgeFinder")
    bankroll = st.sidebar.number_input(
        "Bankroll ($)", min_value=0.0, value=float(settings["bankroll"]),
        step=50.0,
    )
    kelly = st.sidebar.select_slider(
        "Kelly fraction",
        options=[0.1, 0.25, 0.5, 1.0],
        value=settings["kelly_multiplier"],
        help="Fraction of full-Kelly to stake. 0.25 (quarter Kelly) is the "
             "standard choice: most of the growth, a fraction of the variance.",
    )
    updated = {"bankroll": bankroll, "kelly_multiplier": kelly}
    if updated != settings:
        config.save_settings(updated)
    quota = odds_api.get_quota()
    if quota:
        st.sidebar.caption(
            f"📡 Odds API requests left this month: **{quota['remaining']}**"
        )
    st.sidebar.caption(
        "Profit comes from betting only when the model's price beats "
        "FanDuel's, and sizing with Kelly. No model wins every night; "
        "never stake money you can't afford to lose. "
        "Problem gambling help: 1-800-GAMBLER."
    )
    return updated


def main() -> None:
    settings = render_sidebar()
    board, evaluator, parlay, log, soccer, ufc, nba = st.tabs([
        "📅 Today's Board", "🎯 Bet Evaluator", "🎰 Parlay Builder",
        "📒 Bet Log", "⚽ Soccer", "🥊 UFC", "🏀 NBA",
    ])
    with board:
        board_tab.render()
    with evaluator:
        evaluator_tab.render(settings)
    with parlay:
        parlay_tab.render(settings)
    with log:
        betlog_tab.render()
    with soccer:
        soccer_tab.render()
    with ufc:
        ufc_tab.render(settings)
    with nba:
        st.subheader("NBA")
        st.info(
            "The NBA season tips off in October. The same Elo engine and EV "
            "pipeline will power the NBA board (K=20, ~70 Elo home edge) — "
            "game data comes from the league's free stats feed once the "
            "season starts."
        )


if __name__ == "__main__":
    main()
