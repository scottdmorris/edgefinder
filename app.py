"""Ball Knowledge: basketball player projections and prop tracking for FanDuel.

Run with:  .venv\\Scripts\\streamlit run app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from edgefinder.data import odds_api
from edgefinder.ui import (
    about_tab, nba_live_tab, nba_parlay_tab, nba_player_tab, nba_record_tab, nba_tab, style,
)

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Ball Knowledge", page_icon=str(ASSETS / "logo-mark.svg"),
                   layout="wide", initial_sidebar_state="collapsed")
st.logo(str(ASSETS / "logo.svg"), icon_image=str(ASSETS / "logo-mark.svg"), size="large")

TABS = [":material/receipt_long: Parlay", ":material/sensors: Live",
        ":material/search: Players", ":material/insights: Picks",
        ":material/verified: Record", ":material/info: About"]


def render_footer() -> None:
    lines = ["Paper tracking only: no money is staked, and no model wins every night. "
             "Never stake money you can't afford to lose. Problem gambling help: 1-800-GAMBLER."]
    quota = odds_api.get_quota()
    if quota:
        lines.append(f"Odds API requests left this month: {quota['remaining']}")
    st.markdown(style.footer(lines), unsafe_allow_html=True)


def main() -> None:
    style.inject()
    parlay, live, players, picks, record, about = st.tabs(TABS)
    with parlay:
        nba_parlay_tab.render()
    with live:
        nba_live_tab.render()
    with players:
        nba_player_tab.render()
    with picks:
        nba_tab.render()
    with record:
        nba_record_tab.render()
    with about:
        about_tab.render()
    render_footer()


if __name__ == "__main__":
    main()
