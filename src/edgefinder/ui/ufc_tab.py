"""UFC: FanDuel lines with manual probability entry.

Deliberately model-free. There is no free MMA stats source rich enough
to model fights honestly (tiny samples, short-notice replacements,
style matchups), so this tab shows the market and lets you price your
own opinion against it instead of pretending an algorithm knows MMA.
"""

import pandas as pd
import streamlit as st

from ..betting import ev, odds_math
from ..data import odds_api
from ..tracking import bet_log
from . import shared


def render(settings: dict) -> None:
    st.subheader("UFC / MMA")
    if not odds_api.get_api_key():
        st.info("Add an Odds API key to pull FanDuel MMA lines.")
        return
    try:
        events = odds_api.fanduel_ufc()
    except odds_api.OddsApiError as exc:
        st.error(f"Could not load MMA odds: {exc}")
        return
    fights = [e for e in events
              if e.get("home_ml") is not None and e.get("away_ml") is not None]
    if not fights:
        st.info("No upcoming fights with FanDuel lines right now.")
        return
    st.caption(
        "No model here, on purpose: free MMA data is too thin to model "
        "honestly. The market probabilities below are FanDuel's own "
        "prices with the vig removed. If your read on a fight differs "
        "from the market's, enter your probability to price it."
    )
    st.dataframe(_to_display(fights), use_container_width=True, hide_index=True)
    _manual_evaluator(fights, settings)


def _to_display(fights: list[dict]) -> pd.DataFrame:
    rows = []
    for f in fights:
        fair_a, fair_b = odds_math.devig_two_way(
            odds_math.implied_prob(f["home_ml"]),
            odds_math.implied_prob(f["away_ml"]),
        )
        rows.append({
            "Fight": f"{f['home']} vs {f['away']}",
            "Starts (UTC)": f.get("commence_time"),
            f"Odds": (f"{shared.fmt_american(f['home_ml'])} / "
                      f"{shared.fmt_american(f['away_ml'])}"),
            "Market prob": f"{fair_a * 100:.0f}% / {fair_b * 100:.0f}%",
        })
    return pd.DataFrame(rows)


def _manual_evaluator(fights: list[dict], settings: dict) -> None:
    st.markdown("**Price your own read**")
    labels = [f"{f['home']} vs {f['away']}" for f in fights]
    choice = st.selectbox("Fight", labels)
    fight = fights[labels.index(choice)]
    fighter = st.radio("Your pick", [fight["home"], fight["away"]],
                       horizontal=True)
    is_home = fighter == fight["home"]
    quoted = fight["home_ml"] if is_home else fight["away_ml"]
    fair_home, fair_away = odds_math.devig_two_way(
        odds_math.implied_prob(fight["home_ml"]),
        odds_math.implied_prob(fight["away_ml"]),
    )
    market_prob = fair_home if is_home else fair_away
    your_prob = st.slider(
        f"Your probability that {fighter} wins",
        min_value=5, max_value=95, value=int(round(market_prob * 100)),
        format="%d%%",
        help="Defaults to the market's devigged probability. Move it "
             "only if you genuinely know something the market hasn't priced.",
    ) / 100.0
    odds = st.number_input("FanDuel odds (American)", value=int(quoted), step=5)
    decimal = odds_math.american_to_decimal(odds)
    ev_value = ev.ev_per_unit(your_prob, decimal)
    recommended = ev.recommended_stake(
        settings["bankroll"], your_prob, decimal,
        kelly_multiplier=settings["kelly_multiplier"],
    )
    st.markdown(shared.ev_verdict(ev_value))
    stake = shared.stake_input(recommended, ev_value, decimal, key="ufc_stake")
    description = f"{fighter} ML ({fight['home']} vs {fight['away']})"
    add_col, log_col = st.columns(2)
    if add_col.button("➕ Add to parlay", key="ufc_add"):
        shared.add_parlay_leg(description, your_prob, odds)
        st.success("Added to parlay builder.")
    if log_col.button("📒 Log this bet", key="ufc_log"):
        bet_log.add_bet("ufc", "ml", description, odds, stake, your_prob)
        st.success(f"Logged: {description}")
