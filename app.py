"""Ball Knowledge: basketball player projections and prop tracking for FanDuel.

Run with:  .venv\\Scripts\\streamlit run app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from edgefinder.data import odds_api
from edgefinder.ui import nba_tab

st.set_page_config(page_title="Ball Knowledge", page_icon="🏀", layout="wide")


def render_sidebar() -> None:
    st.sidebar.title("🏀 Ball Knowledge")
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
    render_sidebar()
    nba_tab.render()


if __name__ == "__main__":
    main()
