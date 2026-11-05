"""Player lookup: search anyone, see how they're playing, and how often they've
cleared a number.

Read-only. Uses the cached game logs and, if the player has a points line
on the latest slate, shows that line and what the models project.
"""

import datetime as dt
import math

import altair as alt
import pandas as pd
import streamlit as st

from ..data import nba_live, nba_stats
from ..tracking import nba_paper, nba_parlay, nba_player_lookup as lookup
from . import shared

HISTORY_SEASONS = 2
CHART_GAMES = 15
SEASON_STATS = [("Points", "pts"), ("Rebounds", "reb"), ("Assists", "ast"),
                ("Minutes", "minutes"), ("3-pointers", "fg3m")]


@st.cache_data(ttl=3600, show_spinner="Loading game logs...")
def _history() -> pd.DataFrame:
    today = dt.date.today()
    try:
        return pd.concat([nba_stats.load_season(season, today=today)
                          for season in nba_stats.recent_seasons(today, HISTORY_SEASONS)],
                         ignore_index=True)
    except nba_stats.NbaDataError:
        return pd.DataFrame()


def render() -> None:
    st.subheader("Player lookup")
    history = _history()
    if history.empty:
        st.warning("Game logs aren't available right now, so players can't be looked up.")
        return
    options = lookup.player_options(history, nba_stats.current_season(dt.date.today())) \
        or lookup.player_options(history)
    player_id = st.selectbox(
        "Search any player", list(options), index=None, format_func=options.get,
        placeholder="Start typing a name…", key="player_pick",
        help="Matches as you type. Accents don't matter: “doncic” finds Dončić.")
    if player_id is None:
        st.caption("Pick a player to see their season averages, recent games, and how "
                   "often they've cleared a number.")
        return
    latest = history[history["player_id"] == player_id].sort_values("game_date").iloc[-1]
    _profile(history, player_id, latest)


def _profile(history: pd.DataFrame, player_id: int, row: pd.Series) -> None:
    games = lookup.player_games(history, player_id)
    season = lookup.current_season_games(games)
    photo, title = st.columns([1, 3], vertical_alignment="center")
    photo.image(nba_parlay.headshot_url(player_id), width=150)
    with title:
        st.markdown(f"## {row['player_name']}")
        logo = nba_live.logo_url(row["team"])
        if logo:
            st.image(logo, width=34)
        st.caption(f"{row['team']}  ·  {lookup.season_averages(season).get('season', '')}  ·  "
                   f"{len(season)} games")
    _averages(season)
    _tonight(player_id)
    st.divider()
    _hit_rate(games, season, player_id)
    st.markdown("#### Recent games")
    st.dataframe(lookup.recent_games(games, 10), use_container_width=True, hide_index=True)


def _averages(season: pd.DataFrame) -> None:
    averages = lookup.season_averages(season)
    for column, (label, stat) in zip(st.columns(len(SEASON_STATS)), SEASON_STATS):
        column.metric(label, f"{averages[stat]:.1f}")


def _tonight(player_id: int) -> None:
    ledger = nba_paper.load_ledger()
    if ledger.empty:
        return
    rows = ledger[(ledger["player_id"] == player_id)
                  & (ledger["game_date"] == ledger["game_date"].max())]
    if rows.empty:
        return
    first = rows.iloc[0]
    projections = rows.drop_duplicates("model_version").set_index("model_version")["model_mean"]
    parts = "  ·  ".join(f"{nba_parlay.model_name(v)}: **{m:.1f}**" for v, m in projections.items())
    st.info(f"**On the slate:** {first['away']} @ {first['home']}. Points line "
            f"**{first['line']:g}** (over {shared.fmt_american(first['over_odds'])}, "
            f"under {shared.fmt_american(first['under_odds'])}). Projected points  {parts}")


def _hit_rate(games: pd.DataFrame, season: pd.DataFrame, player_id: int) -> None:
    st.markdown("#### How often does he clear a number?")
    stat_name = st.radio("Stat", list(lookup.STATS), horizontal=True, key="lookup_stat")
    stat = lookup.STATS[stat_name]
    default = math.floor(float(season[stat].mean())) + 0.5       # a line near his average
    line = st.number_input(f"{stat_name} line", min_value=0.0, step=0.5, value=default,
                           key=f"lookup_line_{player_id}_{stat}")
    recent = lookup.hit_rate(games, stat, line, last=10)
    year = lookup.hit_rate(season, stat, line)
    st.markdown(
        f"Over **{line:g}** {stat_name.lower()}: **{recent['over']} of the last "
        f"{recent['games']}** games ({recent['over_pct']:.0f}%) and **{year['over']} of "
        f"{year['games']}** this season ({year['over_pct']:.0f}%).")
    _bar_chart(games, stat, stat_name, line)


def _bar_chart(games: pd.DataFrame, stat: str, stat_name: str, line: float) -> None:
    recent = games.sort_values("game_date").tail(CHART_GAMES)
    bars = pd.DataFrame({
        "Game": [f"{d:%b %d} {'vs' if h else '@'} {o}" for d, h, o in
                 zip(recent["game_date"], recent["is_home"], recent["opponent"])],
        stat_name: recent[stat].to_numpy(),
        "Result": ["Over" if v > line else "Under" if v < line else "Push"
                   for v in recent[stat]],
    })
    base = alt.Chart(bars)
    chart = base.mark_bar().encode(
        x=alt.X("Game:N", sort=None, title=None, axis=alt.Axis(labelAngle=-60)),
        y=alt.Y(f"{stat_name}:Q"),
        color=alt.Color("Result:N", legend=None, scale=alt.Scale(
            domain=["Over", "Under", "Push"], range=["#1493FF", "#46557A", "#8FA0BC"])),
        tooltip=["Game", stat_name, "Result"])
    rule = alt.Chart(pd.DataFrame({"line": [line]})).mark_rule(
        color="#F5B83D", strokeDash=[6, 4], size=2).encode(y=alt.Y("line:Q", title=stat_name))
    st.altair_chart((chart + rule).properties(height=260), use_container_width=True)
    st.caption(f"Last {len(bars)} games. Blue bars cleared the line; the dashed line is {line:g}.")
