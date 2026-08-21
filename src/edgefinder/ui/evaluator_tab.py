"""Bet Evaluator: price any single bet against the model.

Two modes: game markets (moneyline / total) using the day's board, and
pitcher strikeout props (enter FanDuel's line manually — prop odds are
expensive on the free API tier).
"""

import streamlit as st

from ..betting import ev, odds_math, poisson
from ..data import mlb_api
from ..models import props
from ..tracking import bet_log
from . import shared


def render(settings: dict) -> None:
    st.subheader("Bet Evaluator")
    mode = st.radio(
        "Bet type", ["Moneyline / Total", "Pitcher strikeout prop"],
        horizontal=True,
    )
    season, date_iso = shared.slate_picker("eval_date")
    try:
        board = shared.cached_board(season, date_iso)
    except Exception as exc:
        st.error(f"Could not load games: {exc}")
        return
    board = shared.upcoming_games(board)
    if not board:
        st.warning(
            "No upcoming games on this slate — pick tomorrow's date to "
            "price the next slate."
        )
        return
    if mode == "Moneyline / Total":
        _game_market(board, settings)
    else:
        _strikeout_prop(board, season, date_iso, settings)


def _pick_game(board: list[dict]) -> dict:
    labels = [f"{g['away']} @ {g['home']}" for g in board]
    choice = st.selectbox("Game", labels)
    return board[labels.index(choice)]


def _game_market(board: list[dict], settings: dict) -> None:
    game = _pick_game(board)
    market = st.selectbox("Market", [
        f"{game['home']} moneyline",
        f"{game['away']} moneyline",
        "Over (total)",
        "Under (total)",
    ])
    if "moneyline" in market:
        is_home = market.startswith(game["home"])
        model_prob = game["p_home"] if is_home else game["p_away"]
        description = f"{market} ({game['away']} @ {game['home']})"
    else:
        if game["model_total"] is None:
            st.warning("No totals model for this game (missing team data).")
            return
        line = st.number_input(
            "FanDuel total line", value=float(game.get("total_line") or 8.5),
            step=0.5,
        )
        probs = poisson.no_push_probs(line, game["model_total"])
        model_prob = probs["over"] if market.startswith("Over") else probs["under"]
        st.caption(f"Model expects {game['model_total']:.2f} total runs.")
        description = f"{market} {line} ({game['away']} @ {game['home']})"
    odds = st.number_input("FanDuel odds (American)", value=-110, step=5)
    _show_verdict(description, model_prob, odds, settings, sport="mlb",
                  bet_type="game")


def _strikeout_prop(
    board: list[dict], season: int, date_iso: str, settings: dict,
) -> None:
    game = _pick_game(board)
    pitchers = [p for p in (
        ("home", game.get("home_pitcher")), ("away", game.get("away_pitcher")),
    ) if p[1]]
    if not pitchers:
        st.warning("No probable pitchers announced for this game yet.")
        return
    side_labels = {name for _, name in pitchers}
    pitcher_name = st.selectbox("Pitcher", sorted(side_labels))
    side = next(s for s, name in pitchers if name == pitcher_name)
    opponent = game["away"] if side == "home" else game["home"]
    expected = _expected_ks(game, side, season, date_iso, opponent)
    if expected is None:
        st.warning(f"Not enough {season} starts to model {pitcher_name}.")
        return
    st.caption(f"Model expects **{expected:.2f} Ks** vs {opponent}.")
    line = st.number_input("FanDuel K line", value=5.5, step=0.5)
    direction = st.radio("Side", ["Over", "Under"], horizontal=True)
    odds = st.number_input("FanDuel odds (American)", value=-115, step=5)
    probs = poisson.no_push_probs(line, expected)
    model_prob = probs["over"] if direction == "Over" else probs["under"]
    description = f"{pitcher_name} {direction} {line} Ks vs {opponent}"
    _show_verdict(description, model_prob, odds, settings, sport="mlb",
                  bet_type="prop")


@st.cache_data(ttl=3600, show_spinner="Fetching pitcher game log...")
def _expected_ks(
    game: dict, side: str, season: int, date_iso: str, opponent: str,
) -> float | None:
    schedule = mlb_api.todays_schedule(date_iso)
    match = next(
        (g for g in schedule if g["home"] == game["home"] and g["away"] == game["away"]),
        None,
    )
    pitcher = (match or {}).get(f"{side}_pitcher")
    if not pitcher:
        return None
    k_log = mlb_api.pitcher_strikeouts_by_start(pitcher["id"], season)
    team_ks = mlb_api.team_hitting_k_per_game(season)
    league_avg = (sum(team_ks.values()) / len(team_ks)) if team_ks else 8.5
    return props.expected_strikeouts(k_log, team_ks.get(opponent), league_avg)


def _show_verdict(
    description: str, model_prob: float, odds: float,
    settings: dict, sport: str, bet_type: str,
) -> None:
    decimal = odds_math.american_to_decimal(odds)
    ev_value = ev.ev_per_unit(model_prob, decimal)
    recommended = ev.recommended_stake(
        settings["bankroll"], model_prob, decimal,
        kelly_multiplier=settings["kelly_multiplier"],
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Model win prob", shared.fmt_pct(model_prob))
    col2.metric("Fair odds", shared.fair_american(model_prob))
    col3.metric("Kelly stake", f"${recommended:,.2f}")
    st.markdown(shared.ev_verdict(ev_value))
    stake = shared.stake_input(recommended, ev_value, decimal,
                               key=f"stake_{description}")
    add_col, log_col = st.columns(2)
    if add_col.button("➕ Add to parlay"):
        shared.add_parlay_leg(description, model_prob, odds)
        st.success("Added to parlay builder.")
    if log_col.button("📒 Log this bet"):
        bet_log.add_bet(sport, bet_type, description, odds, stake, model_prob)
        st.success(f"Logged: {description} at {shared.fmt_american(odds)} for ${stake:,.2f}")
