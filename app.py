"""Ball Knowledge: basketball player projections and prop tracking for FanDuel.

Run with:  .venv\\Scripts\\streamlit run app.py
"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from edgefinder.data import job_health, odds_api
from edgefinder.ui import (
    about_tab, nba_live_tab, nba_parlay_tab, nba_player_tab, nba_record_tab, nba_tab, style,
)

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Ball Knowledge", page_icon=str(ASSETS / "logo-mark.svg"),
                   layout="wide", initial_sidebar_state="collapsed")

TABS = [":material/receipt_long: Parlay", ":material/sensors: Live",
        ":material/search: Players", ":material/insights: Picks",
        ":material/verified: Record", ":material/info: About"]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _logo_src() -> str:
    """The logo mark inlined, so the top bar needs no extra request."""
    import base64
    try:
        data = (ASSETS / "logo-mark.svg").read_bytes()
    except OSError:
        return ""
    return "data:image/svg+xml;base64," + base64.b64encode(data).decode("ascii")


def render_app_bar() -> None:
    """Logo and name, with what is happening right now: games on, and when lines were checked."""
    chips = []
    try:
        live = [g for g in nba_live_tab._games() if g.status == nba_live_tab.nba_live.LIVE]
        if live:
            chips.append((f"{len(live)} live", "live"))
    except Exception:       # noqa: BLE001 - the bar must never stop the app
        pass
    snapshot = job_health.snapshot_health(job_health.load(), _now())
    chips.append((snapshot.text.replace("Lines last checked ", "Lines "),
                  "" if snapshot.level == "ok" else "warn"))
    st.markdown(style.app_bar(_logo_src(), "Ball Knowledge", chips), unsafe_allow_html=True)


def render_health_notice() -> None:
    """Say so, loudly, when the jobs that record picks have stopped or failed."""
    beats, now = job_health.load(), _now()
    problem = job_health.worst(job_health.snapshot_health(beats, now),
                               job_health.settle_health(beats, now))
    if problem is not None:
        st.markdown(style.notice(problem.text), unsafe_allow_html=True)


def render_footer() -> None:
    lines = ["Paper tracking only: no money is staked, and no model wins every night. "
             "Never stake money you can't afford to lose. Problem gambling help: 1-800-GAMBLER."]
    lines.append(job_health.snapshot_health(job_health.load(), _now()).text)
    quota = odds_api.get_quota()
    if quota:
        lines.append(f"Odds API requests left this month: {quota['remaining']}")
    st.markdown(style.footer(lines), unsafe_allow_html=True)


def main() -> None:
    style.inject()
    render_app_bar()
    render_health_notice()
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
