"""Streamlit helpers shared across tabs."""

import datetime as dt

import streamlit as st

from .. import pipeline
from ..betting import odds_math

PARLAY_KEY = "parlay_legs"


@st.cache_data(ttl=900, show_spinner="Training model on this season's games...")
def cached_board(season: int, date_iso: str) -> list[dict]:
    return pipeline.build_board(season, date_iso)


def current_season_and_date() -> tuple[int, str]:
    today = dt.date.today()
    return today.year, today.isoformat()


def slate_picker(key: str) -> tuple[int, str]:
    """Date selector defaulting to today; late at night the next slate
    is usually the one worth pricing."""
    season, today_iso = current_season_and_date()
    picked = st.date_input(
        "Slate date", dt.date.fromisoformat(today_iso), key=key,
    )
    return season, picked.isoformat()


def upcoming_games(board: list[dict]) -> list[dict]:
    return [g for g in board if g.get("status") in (None, "Preview")]


def fmt_american(american: float | None) -> str:
    if american is None:
        return "—"
    return f"+{american:.0f}" if american > 0 else f"{american:.0f}"


def fair_american(prob: float) -> str:
    try:
        return fmt_american(odds_math.prob_to_american(prob))
    except ValueError:
        return "—"


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def add_parlay_leg(description: str, model_prob: float, american_odds: float) -> None:
    legs = st.session_state.setdefault(PARLAY_KEY, [])
    st.session_state[PARLAY_KEY] = legs + [{
        "description": description,
        "model_prob": model_prob,
        "american_odds": american_odds,
    }]


def stake_input(
    recommended: float, ev_value: float, decimal_odds: float, key: str,
) -> float:
    """User-chosen stake with dollar expectations and an overstake
    warning when it exceeds Kelly guidance."""
    default = recommended if recommended > 0 else 0.0
    stake = st.number_input(
        "Your stake ($)", min_value=0.0, value=float(default), step=1.0,
        key=key,
    )
    if stake > 0:
        win_profit = stake * (decimal_odds - 1.0)
        expected = stake * ev_value
        st.caption(
            f"Wins ${win_profit:,.2f} · expected value **${expected:+,.2f}** "
            "per bet over the long run"
        )
        if ev_value <= 0:
            st.warning(
                "This bet is -EV: every dollar staked expects to lose "
                f"{abs(ev_value) * 100:.1f}¢ on average."
            )
        elif recommended > 0 and stake > recommended * 1.5:
            st.warning(
                f"⚠️ Overstaked: ${stake:,.2f} is "
                f"{stake / recommended:.1f}× the Kelly guidance of "
                f"${recommended:,.2f}. Oversized bets turn a winning "
                "strategy into a bankroll-buster — variance compounds "
                "faster than edge."
            )
    return stake


def ev_verdict(ev_value: float) -> str:
    ev_value = round(ev_value, 4)  # avoid float dust reading as "-0.0%"
    if ev_value >= 0.03:
        return f"🟢 +EV: {ev_value * 100:+.1f}% expected return"
    if ev_value >= 0.0:
        return f"🟡 Marginal: {ev_value * 100:+.1f}% expected return"
    return f"🔴 -EV: {ev_value * 100:+.1f}% expected return — skip this"
