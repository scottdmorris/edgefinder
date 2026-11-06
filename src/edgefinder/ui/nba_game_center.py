"""The game center for one game: quarter scores, a shot chart, team stats side
by side, leaders, the play-by-play and the full box score.

Modeled on how sports apps present a live game: Stats, Plays and Box score
tabs under a score header. Everything comes from one `GameDetail`.
"""

from html import escape

import pandas as pd
import streamlit as st

from ..data import nba_live
from ..data.nba_live import GameDetail, LiveGame
from ..tracking import nba_game_view as view
from ..tracking import nba_parlay
from . import style, team_colors

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
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;align-items:center'>"
        f"<span>◀ {_team_tag(game.away, colors[0])} {away['made']}-{away['attempts']}</span>"
        f"<span style='opacity:.65'>● made &nbsp; ✕ missed</span>"
        f"<span>{_team_tag(game.home, colors[1])} {home['made']}-{home['attempts']} ▶</span>"
        f"</div>",
        unsafe_allow_html=True)
    st.markdown(court(game, detail.shots, shots, colors), unsafe_allow_html=True)


def _team_tag(code: str, color: str) -> str:
    """The team's logo and name, with a small swatch of the color its shots are drawn in."""
    logo = nba_live.logo_url(code)
    image = f"<img src='{logo}' width='18' style='vertical-align:-3px'> " if logo else ""
    return f"<span style='color:{color}'>●</span> {image}<b>{escape(code)}</b>"


def _period_label(period: int) -> str:
    return f"Q{period}" if period <= 4 else f"OT{period - 4}"


def court(game: LiveGame, all_shots, shown, colors: tuple[str, str]) -> str:
    """The shot chart for `shown` (one period or all), with shots new since the last refresh
    marked to pop in. The away team shoots at the left basket, the home team at the right."""
    key = f"seen_shots_{game.game_id}"
    fresh = view.new_plays(st.session_state.get(key), list(range(len(all_shots))))
    st.session_state[key] = len(all_shots) - 1
    by_team = dict(zip((game.away, game.home), colors))
    index = {id(s): i for i, s in enumerate(all_shots)}
    placed = dict(zip(map(id, shown), view.to_ends(shown, game.away, game.home)))
    shots = [{"x": placed[id(s)].x, "y": placed[id(s)].y, "made": s.made,
              "color": by_team.get(s.team, ""), "fresh": index.get(id(s)) in fresh,
              "label": f"{s.player} · {'made' if s.made else 'missed'} · {s.distance:.0f} ft · "
                       f"{_period_label(s.period)}"} for s in shown]
    lines = {name: list(zip(group["x"], group["y"]))
             for name, group in view.court_lines().sort_values("order").groupby("line", sort=False)}
    return style.court_svg(lines, shots, team_colors.team_color(game.home),
                           nba_live.logo_url(game.home))


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
