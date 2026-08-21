"""Parlay Builder: data-driven suggestions plus a manual builder with
honest compound-EV accounting."""

import pandas as pd
import streamlit as st

from ..betting import ev as ev_mod
from ..betting import odds_math, suggest
from ..betting.parlay import ParlayLeg, leg_marginal_ev, parlay_decimal_odds, parlay_ev, parlay_true_prob
from ..tracking import bet_log
from . import shared


def render(settings: dict) -> None:
    st.subheader("Parlay Builder")
    _suggestions_section(settings)
    st.divider()
    st.markdown("### Your ticket")
    raw_legs = st.session_state.get(shared.PARLAY_KEY, [])
    if not raw_legs:
        st.info(
            "No legs on the ticket yet. Load a suggested parlay above, or "
            "add legs from the **Bet Evaluator** tab."
        )
        return
    legs = [ParlayLeg(l["description"], l["model_prob"], l["american_odds"])
            for l in raw_legs]
    _legs_table(legs, raw_legs)
    quoted = st.number_input(
        "FanDuel quoted parlay odds (American, 0 = use product of legs)",
        value=0, step=5,
        help="FanDuel SGP pricing usually pays LESS than the product of "
             "the legs. Enter the actual quote to see the real EV.",
    )
    quoted_decimal = odds_math.american_to_decimal(quoted) if quoted != 0 else None
    payout = quoted_decimal or parlay_decimal_odds(legs)
    true_prob = parlay_true_prob(legs)
    total_ev = parlay_ev(legs, quoted_decimal)
    recommended = ev_mod.recommended_stake(
        settings["bankroll"], true_prob, payout,
        kelly_multiplier=settings["kelly_multiplier"],
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("True hit prob", shared.fmt_pct(true_prob))
    col2.metric("Payout odds", shared.fmt_american(odds_math.decimal_to_american(payout)))
    col3.metric("Fair odds", shared.fair_american(true_prob))
    col4.metric("Kelly stake", f"${recommended:,.2f}")
    st.markdown(shared.ev_verdict(total_ev))
    stake = shared.stake_input(recommended, total_ev, payout, key="parlay_stake")
    if len(legs) > 1:
        st.caption(
            "⚠️ Legs are assumed independent. Same-game legs are usually "
            "correlated, which makes the true-probability estimate wrong — "
            "treat SGP numbers as optimistic."
        )
    action_col1, action_col2 = st.columns(2)
    if action_col1.button("📒 Log this parlay"):
        description = " + ".join(l.description for l in legs)
        american = odds_math.decimal_to_american(payout)
        bet_log.add_bet("multi", "parlay", description, american, stake, true_prob)
        st.success("Parlay logged.")
    if action_col2.button("🗑️ Clear all legs"):
        st.session_state[shared.PARLAY_KEY] = []
        st.rerun()


def _suggestions_section(settings: dict) -> None:
    st.markdown("### 🤖 Suggested parlays (from the data)")
    season, date_iso = shared.slate_picker("suggest_date")
    try:
        board = shared.cached_board(season, date_iso)
    except Exception as exc:
        st.error(f"Could not load the board: {exc}")
        return
    board = shared.upcoming_games(board)
    if not board:
        st.info(
            "No upcoming games on this slate (they may have already "
            "started). Pick tomorrow's date to price the next slate."
        )
        return
    num_legs = st.slider("Legs per parlay", 2, 4, 2)
    candidates = suggest.board_candidate_legs(board)
    odds_mode = any(leg.american_odds is not None for leg in candidates)
    suggestions = suggest.suggest_parlays(candidates, num_legs=num_legs)
    if odds_mode and not suggestions:
        st.warning(
            "No parlay clears positive EV at today's FanDuel prices. "
            "That is the normal, honest answer most days — forcing a "
            "ticket anyway is how parlays lose. Check back when lines move."
        )
        return
    if not odds_mode:
        st.info(
            "No odds key configured, so these are the model's most likely "
            "combos ranked by hit probability. Compare the **fair odds** "
            "shown against FanDuel's quoted payout: if FanDuel pays MORE "
            "than fair, the parlay is +EV; if it pays less, skip it."
        )
    for rank, suggestion in enumerate(suggestions, start=1):
        _render_suggestion(rank, suggestion, odds_mode, settings)


def _render_suggestion(
    rank: int, suggestion, odds_mode: bool, settings: dict,
) -> None:
    prob = suggestion.true_prob
    fair = shared.fair_american(prob)
    if odds_mode:
        payout = shared.fmt_american(
            odds_math.decimal_to_american(suggestion.decimal_odds))
        headline = (f"#{rank} · hits {shared.fmt_pct(prob)} · pays {payout} "
                    f"· EV {suggestion.ev * 100:+.1f}%")
    else:
        headline = f"#{rank} · hits {shared.fmt_pct(prob)} · fair odds {fair}"
    with st.expander(headline, expanded=(rank == 1)):
        for leg in suggestion.legs:
            odds_txt = (shared.fmt_american(leg.american_odds)
                        if leg.american_odds is not None
                        else f"fair {shared.fair_american(leg.model_prob)}")
            st.markdown(
                f"- **{leg.description}** — model "
                f"{shared.fmt_pct(leg.model_prob)} at {odds_txt}"
            )
        if odds_mode:
            stake = ev_mod.recommended_stake(
                settings["bankroll"], prob, suggestion.decimal_odds,
                kelly_multiplier=settings["kelly_multiplier"],
            )
            st.caption(f"Suggested stake: ${stake:,.2f}")
        else:
            st.caption(
                f"Bet only if FanDuel quotes better than {fair}."
            )
        if st.button("Load into ticket", key=f"load_suggestion_{rank}"):
            st.session_state[shared.PARLAY_KEY] = [
                {
                    "description": leg.description,
                    "model_prob": leg.model_prob,
                    "american_odds": (
                        leg.american_odds if leg.american_odds is not None
                        else odds_math.prob_to_american(leg.model_prob)
                    ),
                }
                for leg in suggestion.legs
            ]
            st.rerun()


def _legs_table(legs: list[ParlayLeg], raw_legs: list[dict]) -> None:
    rows = []
    for i, leg in enumerate(legs):
        rows.append({
            "Leg": leg.description,
            "Model prob": shared.fmt_pct(leg.model_prob),
            "Odds": shared.fmt_american(leg.american_odds),
            "Marginal EV": shared.fmt_pct(leg_marginal_ev(legs, i)),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        "Marginal EV = how much this leg changes the ticket's EV. "
        "Negative-marginal legs are draining the parlay."
    )
    remove_options = [f"{i}: {leg.description}" for i, leg in enumerate(legs)]
    to_remove = st.selectbox("Remove a leg", ["(none)"] + remove_options)
    if to_remove != "(none)" and st.button("Remove selected leg"):
        index = int(to_remove.split(":")[0])
        st.session_state[shared.PARLAY_KEY] = [
            l for i, l in enumerate(raw_legs) if i != index
        ]
        st.rerun()
