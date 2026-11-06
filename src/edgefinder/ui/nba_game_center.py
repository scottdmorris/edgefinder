"""The game center for one game: quarter scores, a shot chart, team stats side
by side, leaders, the play-by-play and the full box score.

Modeled on how sports apps present a live game: Stats, Plays and Box score
tabs under a score header. Everything comes from one `GameDetail`.
"""

import altair as alt
import pandas as pd
import streamlit as st

from ..data import nba_live
from ..data.nba_live import GameDetail, LiveGame
from ..tracking import nba_game_view as view
from ..tracking import nba_parlay
from . import style, team_colors

COURT_COLOR = "#8B98A5"
FLOOR_TINT = 0.24            # how much of the home team's color shows in the floor
LOGO_SIZE = 90
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
        _play_feed(detail, game)
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
    colors = team_colors.matchup_colors(game.away, game.home)
    st.caption(f"Home court: {game.home}")
    st.markdown(
        f"{_team_tag(game.away, colors[0])} {away['made']}-{away['attempts']}"
        f"&nbsp;&nbsp;&nbsp;&nbsp; {_team_tag(game.home, colors[1])} "
        f"{home['made']}-{home['attempts']}"
        f"&nbsp;&nbsp;&nbsp;&nbsp; <span style='opacity:.65'>● made &nbsp; ✕ missed</span>",
        unsafe_allow_html=True)
    st.altair_chart(_court_chart(shots, game, colors), use_container_width=True)


def _team_tag(code: str, color: str) -> str:
    """The team's logo and name, with a small swatch of the color its shots are drawn in."""
    logo = nba_live.logo_url(code)
    image = f"<img src='{logo}' width='18' style='vertical-align:-3px'> " if logo else ""
    return f"<span style='color:{color}'>●</span> {image}**{code}**"


def _period_label(period: int) -> str:
    return f"Q{period}" if period <= 4 else f"OT{period - 4}"


def court_floor(home: str) -> alt.Chart:
    """The home team's floor: their color as a wash across the court, their logo at center
    court (their tricode in big letters when no logo is on file)."""
    axis_free = {"axis": None, "scale": alt.Scale(domain=[0, 100], nice=False)}
    wash = alt.Chart(pd.DataFrame({"x": [0], "x2": [100], "y": [0], "y2": [100]})).mark_rect(
        color=team_colors.rgba(team_colors.team_color(home), FLOOR_TINT)).encode(
        x=alt.X("x:Q", **axis_free), x2="x2:Q", y=alt.Y("y:Q", **axis_free), y2="y2:Q")
    logo = nba_live.logo_url(home)
    center = pd.DataFrame({"x": [50], "y": [50], "url": [logo], "name": [home]})
    mark = (alt.Chart(center).mark_image(width=LOGO_SIZE, height=LOGO_SIZE).encode(
                x=alt.X("x:Q", **axis_free), y=alt.Y("y:Q", **axis_free), url="url:N")
            if logo else
            alt.Chart(center).mark_text(fontSize=44, fontWeight="bold", opacity=0.3,
                                        color="#E7E9EA").encode(
                x=alt.X("x:Q", **axis_free), y=alt.Y("y:Q", **axis_free), text="name:N"))
    return wash, mark


def foul_lines(game: LiveGame, detail: GameDetail) -> str:
    """Team fouls and players in foul trouble for both teams, one team per line."""
    lines = [view.foul_line(team, detail.team_stats, detail.players)
             for team in (game.away, game.home)]
    return "  \n".join(line for line in lines if line)


def _court_chart(shots, game: LiveGame, colors: tuple[str, str]) -> alt.Chart:
    axis_free = {"axis": None, "scale": alt.Scale(domain=[0, 100], nice=False)}
    floor, logo = court_floor(game.home)
    court = alt.Chart(view.court_lines()).mark_line(color=COURT_COLOR, strokeWidth=1.4).encode(
        x=alt.X("x:Q", **axis_free), y=alt.Y("y:Q", **axis_free),
        detail="line:N", order="order:Q")
    table = view.shot_table(shots)
    color = alt.Color("Team:N", legend=None, scale=alt.Scale(
        domain=[game.away, game.home], range=list(colors)))
    tooltip = ["Player", "Team", "Result", "Distance (ft)", "Period"]
    made = alt.Chart(table[table["Result"] == "Made"]).mark_circle(size=70, opacity=0.9).encode(
        x=alt.X("x:Q", **axis_free), y=alt.Y("y:Q", **axis_free), color=color, tooltip=tooltip)
    missed = alt.Chart(table[table["Result"] == "Missed"]).mark_point(
        shape="cross", size=55, strokeWidth=1.6, opacity=0.85).encode(
        x=alt.X("x:Q", **axis_free), y=alt.Y("y:Q", **axis_free), color=color, tooltip=tooltip)
    return (floor + court + logo + missed + made).properties(height=300).configure_view(
        strokeWidth=0)


def _team_comparison(game: LiveGame, detail: GameDetail) -> None:
    rows = view.comparison_rows(detail.team_stats.get(game.away, {}),
                                detail.team_stats.get(game.home, {}))
    if not rows:
        return
    st.markdown("**Team stats**")
    away_color, home_color = team_colors.matchup_colors(game.away, game.home)
    st.markdown(
        f"<div style='display:flex;justify-content:space-between'>"
        f"<span>{_team_tag(game.away, away_color)}</span>"
        f"<span>{_team_tag(game.home, home_color)}</span></div>", unsafe_allow_html=True)
    st.markdown("".join(
        style.compare_bar(r["label"], r["away_text"], r["home_text"], r["away_share"],
                          r["ahead"], away_color, home_color)
        for r in rows), unsafe_allow_html=True)


def _leaders(game: LiveGame, detail: GameDetail) -> None:
    st.markdown("**Game leaders**")
    for team in (game.away, game.home):
        for stat, player in view.leaders(detail.players, team).items():
            if player is None:
                continue
            value = {"Points": player.points, "Rebounds": player.rebounds,
                     "Assists": player.assists}[stat]
            st.markdown(style.leader_card(
                nba_parlay.headshot_url(player.player_id), player.name, team, stat, value,
                accent=team_colors.team_color(team), logo=nba_live.logo_url(team)),
                unsafe_allow_html=True)


def _play_feed(detail: GameDetail, game: LiveGame | None = None) -> None:
    if not detail.plays:
        st.caption("No plays yet.")
        return
    key = f"seen_play_{game.game_id}" if game else "seen_play"
    fresh = view.new_plays(st.session_state.get(key), [p.order for p in detail.plays])
    st.session_state[key] = max(p.order for p in detail.plays)
    colors = dict(zip((game.away, game.home), team_colors.matchup_colors(game.away, game.home))) \
        if game else {}
    latest = list(reversed(detail.plays[-FEED_LENGTH:]))
    st.markdown("".join(
        style.feed_item(f"{p.period} {p.clock}", p.text, p.score, p.order in fresh,
                        colors.get(p.team, "")) for p in latest),
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
