"""The game center for one game: quarter scores, a shot chart, team stats side
by side, leaders, the play-by-play and the full box score.

Modeled on how sports apps present a live game: Stats, Plays and Box score
tabs under a score header. Everything comes from one `GameDetail`.
"""

import altair as alt
import pandas as pd
import streamlit as st

from ..data.nba_live import GameDetail, LiveGame
from ..tracking import nba_game_view as view
from ..tracking import nba_parlay
from . import style

AWAY_COLOR, HOME_COLOR = "#1493FF", "#F5B83D"
COURT_COLOR = "#3b4a6b"
FEED_LENGTH = 14
ALL_PERIODS = "All"


def render(game: LiveGame, detail: GameDetail) -> None:
    stats, plays, box = st.tabs(["Stats", "Plays", "Box score"])
    with stats:
        _quarters(game, detail)
        _shot_chart(game, detail)
        _team_comparison(game, detail)
        _leaders(game, detail)
    with plays:
        _play_feed(detail)
    with box:
        _box_score(game, detail)


def _quarters(game: LiveGame, detail: GameDetail) -> None:
    table = view.quarter_table(detail.period_scores, game.away, game.home,
                               game.away_score, game.home_score)
    st.dataframe(table, use_container_width=True)


def _shot_chart(game: LiveGame, detail: GameDetail) -> None:
    st.markdown("**Shot chart**")
    if not detail.shots:
        st.caption("No shots with a location yet.")
        return
    periods = sorted({s.period for s in detail.shots})
    labels = {ALL_PERIODS: ALL_PERIODS, **{p: _period_label(p) for p in periods}}
    choice = style.choose("Period", list(labels), "shot_period", format_func=labels.get)
    shots = view.shots_in_period(detail.shots, None if choice == ALL_PERIODS else choice)

    away, home = (view.shot_summary(shots, team) for team in (game.away, game.home))
    st.markdown(
        f"<span style='color:{AWAY_COLOR}'>●</span> **{game.away}** "
        f"{away['made']}-{away['attempts']} "
        f"&nbsp;&nbsp;&nbsp; <span style='color:{HOME_COLOR}'>●</span> **{game.home}** "
        f"{home['made']}-{home['attempts']} "
        f"&nbsp;&nbsp;&nbsp; <span style='opacity:.65'>● made &nbsp; ✕ missed</span>",
        unsafe_allow_html=True)
    st.altair_chart(_court_chart(shots, game), use_container_width=True)


def _period_label(period: int) -> str:
    return f"Q{period}" if period <= 4 else f"OT{period - 4}"


def _court_chart(shots, game: LiveGame) -> alt.Chart:
    axis_free = {"axis": None, "scale": alt.Scale(domain=[0, 100], nice=False)}
    court = alt.Chart(view.court_lines()).mark_line(color=COURT_COLOR, strokeWidth=1.4).encode(
        x=alt.X("x:Q", **axis_free), y=alt.Y("y:Q", **axis_free),
        detail="line:N", order="order:Q")
    table = view.shot_table(shots)
    color = alt.Color("Team:N", legend=None, scale=alt.Scale(
        domain=[game.away, game.home], range=[AWAY_COLOR, HOME_COLOR]))
    tooltip = ["Player", "Team", "Result", "Distance (ft)", "Period"]
    made = alt.Chart(table[table["Result"] == "Made"]).mark_circle(size=70, opacity=0.9).encode(
        x=alt.X("x:Q", **axis_free), y=alt.Y("y:Q", **axis_free), color=color, tooltip=tooltip)
    missed = alt.Chart(table[table["Result"] == "Missed"]).mark_point(
        shape="cross", size=55, strokeWidth=1.6, opacity=0.85).encode(
        x=alt.X("x:Q", **axis_free), y=alt.Y("y:Q", **axis_free), color=color, tooltip=tooltip)
    return (court + missed + made).properties(height=300).configure_view(strokeWidth=0)


def _team_comparison(game: LiveGame, detail: GameDetail) -> None:
    rows = view.comparison_rows(detail.team_stats.get(game.away, {}),
                                detail.team_stats.get(game.home, {}))
    if not rows:
        return
    st.markdown("**Team stats**")
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;font-weight:700'>"
        f"<span style='color:{AWAY_COLOR}'>{game.away}</span>"
        f"<span style='color:{HOME_COLOR}'>{game.home}</span></div>", unsafe_allow_html=True)
    st.markdown("".join(
        style.compare_bar(r["label"], r["away_text"], r["home_text"], r["away_share"], r["ahead"])
        for r in rows), unsafe_allow_html=True)


def _leaders(game: LiveGame, detail: GameDetail) -> None:
    st.markdown("**Game leaders**")
    for team in (game.away, game.home):
        for stat, player in view.leaders(detail.players, team).items():
            if player is None:
                continue
            value = {"Points": player.points, "Rebounds": player.rebounds,
                     "Assists": player.assists}[stat]
            st.markdown(style.leader_card(nba_parlay.headshot_url(player.player_id), player.name,
                                          team, stat, value), unsafe_allow_html=True)


def _play_feed(detail: GameDetail) -> None:
    if not detail.plays:
        st.caption("No plays yet.")
        return
    latest = list(reversed(detail.plays[-FEED_LENGTH:]))
    st.markdown("".join(
        style.feed_item(f"{p.period} {p.clock}", p.text, p.score) for p in latest),
        unsafe_allow_html=True)


def _box_score(game: LiveGame, detail: GameDetail) -> None:
    team = style.choose("Team", [game.away, game.home], "box_team")
    for heading, starters in (("Starters", True), ("Bench", False)):
        table = view.box_table(detail.players, team, starters)
        if table.empty:
            continue
        st.markdown(f"**{heading}**")
        table.insert(0, "", [nba_parlay.headshot_url(pid) for pid in table.pop("player_id")])
        st.dataframe(table, use_container_width=True, hide_index=True, row_height=44,
                     column_config={"": st.column_config.ImageColumn(" ", width="small")})
    st.caption("🏀 marks players on the court right now.")


def timeout_line(game: LiveGame) -> str:
    """Timeouts left and bonus status for the score header."""
    def side(code: str, timeouts: int, bonus: bool) -> str:
        return f"**{code}** {style.dots(timeouts)}{' · bonus' if bonus else ''}"
    return (f"{side(game.away, game.away_timeouts, game.away_bonus)}"
            f"  &nbsp;|&nbsp;  {side(game.home, game.home_timeouts, game.home_bonus)}")
