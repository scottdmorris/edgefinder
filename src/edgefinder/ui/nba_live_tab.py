"""Live: your slip and every game on tonight's slate, updating while games are on.

Reads NBA's free live feed (no key, no Odds API requests) and refreshes
itself every half minute. Your slip is whatever is picked in the Parlay
builder tab; any game on the slate can be opened for its play-by-play and
box score.
"""

from dataclasses import replace

import pandas as pd
import streamlit as st

from ..betting.odds_math import american_to_decimal
from ..data import nba_live
from ..tracking import nba_parlay, nba_slip_tracker
from . import nba_parlay_tab, style

REFRESH_SECONDS = 30
FEED_LENGTH = 14
STATE_NAMES = {nba_live.SCHEDULED: "upcoming", nba_live.LIVE: "live", nba_live.FINAL: "final"}
BADGES = {
    nba_slip_tracker.HIT: ("hit", "Hit"),
    nba_slip_tracker.ALIVE: ("alive", "Alive"),
    nba_slip_tracker.MISSED: ("missed", "Missed"),
    nba_slip_tracker.NOT_STARTED: ("neutral", "Not started"),
    nba_slip_tracker.VOID: ("neutral", "Void"),
}


@st.cache_data(ttl=15, show_spinner=False)
def _games() -> list[nba_live.LiveGame]:
    return nba_live.fetch_games()


@st.cache_data(ttl=15, show_spinner=False)
def _box(game_id: str) -> dict[int, nba_live.PlayerLine]:
    return nba_live.fetch_box(game_id)


@st.cache_data(ttl=15, show_spinner=False)
def _plays(game_id: str, away: str, home: str) -> list[nba_live.Play]:
    return nba_live.fetch_plays(game_id, away, home)


def render() -> None:
    st.subheader("Live")
    st.caption(f"Updates every {REFRESH_SECONDS} seconds while games are on. "
               "Data comes from NBA's own live feed.")
    _live()


@st.fragment(run_every=REFRESH_SECONDS)
def _live() -> None:
    try:
        games = _games()
    except nba_live.LiveDataError as error:
        st.warning(f"{error}. It tries again on its own in {REFRESH_SECONDS} seconds.")
        return
    if not games:
        st.info("No NBA games on the live scoreboard right now.")
        return
    _slip(games)
    st.divider()
    _scoreboard(games)
    st.divider()
    _game_detail(games)


def _slip(games: list[nba_live.LiveGame]) -> None:
    st.markdown("#### Your slip")
    chosen = nba_parlay_tab.selected_legs()
    if chosen is None:
        st.info("Add bets in the **Parlay builder** tab and they show up here, "
                "with a live read on whether each one is hitting.")
        return
    try:
        progress = nba_slip_tracker.track_slip(chosen, games, _box)
    except nba_live.LiveDataError as error:
        st.warning(str(error))
        return

    overall = nba_slip_tracker.slip_status(list(progress["Status"]))
    kind, word = BADGES[overall]
    hits = int((progress["Status"] == nba_slip_tracker.HIT).sum())
    st.markdown(style.slip_summary(
        "YOUR SLIP", word, [("Bets hit", f"{hits} of {len(progress)}"),
                            *_stake_facts(chosen)]), unsafe_allow_html=True)
    for bet in progress.itertuples():
        kind, word = BADGES[bet.Status]
        player, wager = bet.Leg.split(" · ", 1)
        st.markdown(style.leg_card(
            nba_parlay.headshot_url(bet.player_id), player, f"{wager}  ·  {bet.Game}", word,
            kind=kind, progress=bet.Progress, detail=bet.Detail), unsafe_allow_html=True)


def _stake_facts(chosen: pd.DataFrame) -> list[tuple[str, str]]:
    """The stake typed in the builder and what the slip pays, if one is set."""
    stake = st.session_state.get("stake", 0.0)
    if not stake:
        return []
    decimal = float(chosen["Odds"].map(american_to_decimal).prod())
    return [("Stake", nba_parlay.money(stake)),
            ("To win", nba_parlay.money(stake * (decimal - 1.0)))]


def _scoreboard(games: list[nba_live.LiveGame]) -> None:
    st.markdown("#### Tonight's games")
    left, right = st.columns(2)
    for index, game in enumerate(games):
        (left if index % 2 == 0 else right).markdown(_card(game), unsafe_allow_html=True)


def _card(game: nba_live.LiveGame) -> str:
    running = game.status == nba_live.LIVE and ("Qtr" in game.status_text
                                                 or game.status_text.startswith("OT"))
    status = f"{game.status_text} {game.clock}".strip() if running else game.status_text
    return style.game_card(game.away, game.home, nba_live.logo_url(game.away),
                           nba_live.logo_url(game.home), game.away_score, game.home_score,
                           status, STATE_NAMES.get(game.status, "upcoming"))


def _game_detail(games: list[nba_live.LiveGame]) -> None:
    st.markdown("#### Any game")
    by_id = {g.game_id: g for g in games}
    default = next((i for i, g in enumerate(games) if g.status == nba_live.LIVE), 0)
    game_id = st.selectbox(
        "Pick a game", list(by_id), index=default, key="live_game",
        format_func=lambda gid: f"{by_id[gid].away} @ {by_id[gid].home}  ·  "
                                f"{by_id[gid].status_text}")
    game = by_id[game_id]
    if game.status < nba_live.LIVE:
        st.markdown(_card(game), unsafe_allow_html=True)
        st.info(f"Tips off at {game.status_text}. The play-by-play and box score appear "
                "once the game starts.")
        return
    try:
        plays = _plays(game.game_id, game.away, game.home)
    except nba_live.LiveDataError as error:
        plays = []
        st.warning(str(error))
    st.markdown(_card(_freshest(game, plays)), unsafe_allow_html=True)
    _play_feed(plays)
    _box_score(game)


def _freshest(game: nba_live.LiveGame, plays: list[nba_live.Play]) -> nba_live.LiveGame:
    """NBA's scoreboard can trail its play-by-play by a minute or more, so for a
    game in progress the score and clock come from the latest play."""
    if game.status != nba_live.LIVE or not plays:
        return game
    latest = plays[-1]
    return replace(game, away_score=latest.away_score, home_score=latest.home_score,
                   status_text=nba_live.period_status(latest.period), clock=latest.clock)


def _play_feed(plays: list[nba_live.Play]) -> None:
    st.markdown("**What just happened**")
    if not plays:
        st.caption("No plays yet.")
        return
    latest = list(reversed(plays[-FEED_LENGTH:]))
    st.markdown("".join(
        style.feed_item(f"{p.period} {p.clock}", p.text, p.score) for p in latest),
        unsafe_allow_html=True)


def _box_score(game: nba_live.LiveGame) -> None:
    st.markdown("**Box score**")
    try:
        box = _box(game.game_id)
    except nba_live.LiveDataError as error:
        st.warning(str(error))
        return
    played = [p for p in box.values() if p.played]
    table = pd.DataFrame({
        "": [nba_parlay.headshot_url(p.player_id) for p in played],
        "Player": [p.name + ("  🏀" if p.on_court else "") for p in played],
        "Team": [p.team for p in played],
        "Pts": [p.points for p in played],
        "Reb": [p.rebounds for p in played],
        "Ast": [p.assists for p in played],
        "Min": [round(p.minutes) for p in played],
    }).sort_values("Pts", ascending=False)
    st.dataframe(table, use_container_width=True, hide_index=True, row_height=44,
                 column_config={"": st.column_config.ImageColumn(" ", width="small")})
    st.caption("🏀 marks players on the court right now.")
