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

REFRESH_SECONDS = 10
DATA_TTL = 8                 # seconds a fetched feed is reused; under the refresh, so each one is new
STATE_NAMES = {nba_live.SCHEDULED: "upcoming", nba_live.LIVE: "live", nba_live.FINAL: "final"}
BADGES = {
    nba_slip_tracker.HIT: ("hit", "Hit"),
    nba_slip_tracker.ALIVE: ("alive", "Alive"),
    nba_slip_tracker.MISSED: ("missed", "Missed"),
    nba_slip_tracker.NOT_STARTED: ("neutral", "Not started"),
    nba_slip_tracker.VOID: ("neutral", "Void"),
}


@st.cache_data(ttl=DATA_TTL, show_spinner=False)
def _games() -> list[nba_live.LiveGame]:
    return nba_live.fetch_games()


@st.cache_data(ttl=DATA_TTL, show_spinner=False)
def _box(game_id: str) -> dict[int, nba_live.PlayerLine]:
    return nba_live.fetch_box(game_id)


@st.cache_data(ttl=DATA_TTL, show_spinner=False)
def _detail(game_id: str, away: str, home: str) -> nba_live.GameDetail:
    return nba_live.fetch_detail(game_id, away, home)


def render() -> None:
    st.subheader("Live")
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
    # the scoreboard feed trails the play-by-play, so live games take their score from the
    # latest play everywhere on the page, and two views of one game can never disagree
    details = {g.game_id: _safe_detail(g) for g in games if g.status == nba_live.LIVE}
    games = [_freshest(g, details[g.game_id].plays) if details.get(g.game_id) else g
             for g in games]
    pops = _pops("live_scores", games)
    _slip(games)
    game = _pick_game(games)
    _open_game(game, details.get(game.game_id), pops.get(game.game_id, (0, 0)))
    st.caption(f"Updates by itself every {REFRESH_SECONDS} seconds. NBA's own live feed.")


def _slip(games: list[nba_live.LiveGame]) -> None:
    """Your slip, tracked bet by bet, shown only when there is one."""
    chosen = nba_parlay_tab.selected_legs()
    if chosen is None:
        return
    st.markdown("#### Your slip")
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
    statuses = dict(zip(progress["Leg"], progress["Status"]))
    flipped = nba_game_view.changed_status(st.session_state.get("slip_statuses", {}), statuses)
    st.session_state["slip_statuses"] = statuses
    for bet in progress.itertuples():
        kind, word = BADGES[bet.Status]
        player, wager = bet.Leg.split(" · ", 1)
        team = teams.get(bet.player_id, "")
        st.markdown(style.leg_card(
            nba_parlay.headshot_url(bet.player_id), player, f"{wager}  ·  {bet.Game}", word,
            kind=kind, progress=bet.Progress, detail=bet.Detail,
            accent=team_colors.team_color(team) if team else "",
            logo=nba_live.logo_url(team) if team else "", flash=bet.Leg in flipped),
            unsafe_allow_html=True)


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


ORDER = {nba_live.LIVE: 0, nba_live.SCHEDULED: 1, nba_live.FINAL: 2}


def _safe_detail(game: nba_live.LiveGame) -> nba_live.GameDetail | None:
    try:
        return _detail(game.game_id, game.away, game.home)
    except nba_live.LiveDataError:
        return None


def _state(game: nba_live.LiveGame) -> str:
    return STATE_NAMES.get(game.status, "upcoming")


def _status(game: nba_live.LiveGame) -> str:
    running = game.status == nba_live.LIVE and ("Qtr" in game.status_text
                                                 or game.status_text.startswith("OT"))
    return f"{game.status_text} {game.clock}".strip() if running else game.status_text


def _pick_game(games: list[nba_live.LiveGame]) -> nba_live.LiveGame:
    """The score strip: every game as a chip with its live score, games on now first."""
    by_id = {g.game_id: g for g in games}
    ranked = sorted(games, key=lambda g: ORDER.get(g.status, 3))

    def label(game_id: str) -> str:
        g = by_id[game_id]
        text = nba_game_view.chip_label(g.away, g.home, g.away_score, g.home_score, _state(g),
                                        g.status_text, g.clock)
        return ("🔴 " if g.status == nba_live.LIVE else "") + text

    return by_id[style.choose("Games", [g.game_id for g in ranked], "live_game",
                              format_func=label)]


def _team_note(game: nba_live.LiveGame, detail: nba_live.GameDetail | None, team: str) -> str:
    """Timeouts left, team fouls and the bonus, for under a team in the header."""
    away = team == game.away
    timeouts = game.away_timeouts if away else game.home_timeouts
    bonus = game.away_bonus if away else game.home_bonus
    fouls = (detail.team_stats.get(team, {}).get("foulsPersonal") if detail else None)
    parts = [style.dots(timeouts)]
    if fouls is not None:
        parts.append(f"{int(fouls)} fouls")
    if bonus:
        parts.append("bonus")
    return " · ".join(parts)


def _hero(game: nba_live.LiveGame, detail, pop: tuple[int, int] = (0, 0)) -> str:
    started = game.status >= nba_live.LIVE
    return style.game_hero(
        game.away, game.home, nba_live.logo_url(game.away), nba_live.logo_url(game.home),
        game.away_score, game.home_score, _status(game), _state(game),
        *team_colors.matchup_colors(game.away, game.home), pop[0], pop[1],
        _team_note(game, detail, game.away) if started else "",
        _team_note(game, detail, game.home) if started else "")


def _open_game(game: nba_live.LiveGame, detail, pop: tuple[int, int]) -> None:
    if game.status < nba_live.LIVE:
        st.markdown(_hero(game, None), unsafe_allow_html=True)
        st.caption(f"Tips off at {game.status_text}. Shots, plays and the box score appear "
                   "once the game starts.")
        return
    detail = detail or _safe_detail(game)
    st.markdown(_hero(game, detail, pop), unsafe_allow_html=True)
    if detail is None:
        st.warning("NBA's live feed isn't answering for this game. It tries again on its own.")
        return
    trouble = [f"{name.split()[-1]} {count} ({team})"
               for team in (game.away, game.home)
               for name, count in nba_game_view.foul_trouble(detail.players, team)]
    if trouble:
        st.caption("Foul trouble: " + ", ".join(trouble))
    nba_game_center.render(game, detail)


def _freshest(game: nba_live.LiveGame, plays: list[nba_live.Play]) -> nba_live.LiveGame:
    """NBA's scoreboard can trail its play-by-play by a minute or more, so for a
    game in progress the score and clock come from the latest play."""
    if game.status != nba_live.LIVE or not plays:
        return game
    latest = plays[-1]
    return replace(game, away_score=latest.away_score, home_score=latest.home_score,
                   status_text=nba_live.period_status(latest.period), clock=latest.clock)


