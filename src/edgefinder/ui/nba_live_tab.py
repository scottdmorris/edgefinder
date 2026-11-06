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
from ..tracking import nba_game_view, nba_parlay, nba_slip_tracker
from . import nba_game_center, nba_parlay_tab, style, team_colors

REFRESH_SECONDS = 30
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
def _detail(game_id: str, away: str, home: str) -> nba_live.GameDetail:
    return nba_live.fetch_detail(game_id, away, home)


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
    _scoreboard(games, _pops("live_scores", games))
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
    teams = nba_parlay_tab.teams_by_player()
    for bet in progress.itertuples():
        kind, word = BADGES[bet.Status]
        player, wager = bet.Leg.split(" · ", 1)
        team = teams.get(bet.player_id, "")
        st.markdown(style.leg_card(
            nba_parlay.headshot_url(bet.player_id), player, f"{wager}  ·  {bet.Game}", word,
            kind=kind, progress=bet.Progress, detail=bet.Detail,
            accent=team_colors.team_color(team) if team else "",
            logo=nba_live.logo_url(team) if team else ""), unsafe_allow_html=True)


def _stake_facts(chosen: pd.DataFrame) -> list[tuple[str, str]]:
    """The stake typed in the builder and what the slip pays, if one is set."""
    stake = st.session_state.get("stake", 0.0)
    if not stake:
        return []
    decimal = float(chosen["Odds"].map(american_to_decimal).prod())
    return [("Stake", nba_parlay.money(stake)),
            ("To win", nba_parlay.money(stake * (decimal - 1.0)))]


def _pops(state_key: str, games: list[nba_live.LiveGame]) -> dict[str, tuple[int, int]]:
    """Points each team scored since this view last refreshed, for the score to pop. The scores
    are remembered under `state_key`; a game seen for the first time pops nothing."""
    scores = {g.game_id: (g.away_score, g.home_score) for g in games}
    changes = nba_game_view.score_deltas(st.session_state.get(state_key, {}), scores)
    st.session_state[state_key] = scores
    return changes


def _scoreboard(games: list[nba_live.LiveGame], pops: dict | None = None) -> None:
    st.markdown("#### Tonight's games")
    pops = pops or {}
    left, right = st.columns(2)
    for index, game in enumerate(games):
        (left if index % 2 == 0 else right).markdown(
            _card(game, pops.get(game.game_id, (0, 0))), unsafe_allow_html=True)


def _card(game: nba_live.LiveGame, pop: tuple[int, int] = (0, 0)) -> str:
    running = game.status == nba_live.LIVE and ("Qtr" in game.status_text
                                                 or game.status_text.startswith("OT"))
    status = f"{game.status_text} {game.clock}".strip() if running else game.status_text
    return style.game_card(game.away, game.home, nba_live.logo_url(game.away),
                           nba_live.logo_url(game.home), game.away_score, game.home_score,
                           status, STATE_NAMES.get(game.status, "upcoming"),
                           team_colors.team_color(game.away), team_colors.team_color(game.home),
                           pop[0], pop[1])


def _game_detail(games: list[nba_live.LiveGame]) -> None:
    st.markdown("#### Any game")
    by_id = {g.game_id: g for g in games}
    # games on the court right now come first, then upcoming, then finished
    order = {nba_live.LIVE: 0, nba_live.SCHEDULED: 1, nba_live.FINAL: 2}
    ranked = sorted(games, key=lambda g: order.get(g.status, 3))
    game_id = style.choose(
        "Pick a game", [g.game_id for g in ranked], "live_game",
        format_func=lambda gid: f"{'🔴 ' if by_id[gid].status == nba_live.LIVE else ''}"
                                f"{by_id[gid].away} @ {by_id[gid].home}")
    game = by_id[game_id]
    if game.status < nba_live.LIVE:
        st.markdown(_card(game), unsafe_allow_html=True)
        st.info(f"Tips off at {game.status_text}. The play-by-play and box score appear "
                "once the game starts.")
        return
    try:
        detail = _detail(game.game_id, game.away, game.home)
    except nba_live.LiveDataError as error:
        st.markdown(_card(game), unsafe_allow_html=True)
        st.warning(str(error))
        return
    game = _freshest(game, detail.plays)
    pop = _pops("live_scores_detail", [game]).get(game.game_id, (0, 0))
    st.markdown(_card(game, pop), unsafe_allow_html=True)
    st.markdown(nba_game_center.timeout_line(game), unsafe_allow_html=True)
    if fouls := nba_game_center.foul_lines(game, detail):
        st.caption(fouls)
    nba_game_center.render(game, detail)


def _freshest(game: nba_live.LiveGame, plays: list[nba_live.Play]) -> nba_live.LiveGame:
    """NBA's scoreboard can trail its play-by-play by a minute or more, so for a
    game in progress the score and clock come from the latest play."""
    if game.status != nba_live.LIVE or not plays:
        return game
    latest = plays[-1]
    return replace(game, away_score=latest.away_score, home_score=latest.home_score,
                   status_text=nba_live.period_status(latest.period), clock=latest.clock)


