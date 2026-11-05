"""Ball Knowledge: basketball player projections and prop tracking for FanDuel.

Run with:  .venv\\Scripts\\streamlit run app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from edgefinder.data import odds_api
from edgefinder.ui import nba_live_tab, nba_parlay_tab, nba_player_tab, nba_tab, style

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Ball Knowledge", page_icon=str(ASSETS / "logo-mark.svg"),
                   layout="wide")
st.logo(str(ASSETS / "logo.svg"), icon_image=str(ASSETS / "logo-mark.svg"), size="large")


def render_sidebar() -> None:
    st.sidebar.title("Ball Knowledge")
    quota = odds_api.get_quota()
    if quota:
        st.sidebar.caption(
            f"📡 Odds API requests left this month: **{quota['remaining']}**"
        )
    st.sidebar.caption(
        "Paper tracking only: no money is staked, and no model wins every "
        "night. Never stake money you can't afford to lose. "
        "Problem gambling help: 1-800-GAMBLER."
    )


def main() -> None:
    style.inject()
    render_sidebar()
    parlay, live, players, picks = st.tabs(
        ["🎰 Parlay builder", "📡 Live", "🔎 Players", "🏀 Picks & tracking"])
    with parlay:
        nba_parlay_tab.render()
    with live:
        nba_live_tab.render()
    with players:
        nba_player_tab.render()
    with picks:
        nba_tab.render()


if __name__ == "__main__":
    main()
