"""Parlay builder: pick legs from the day's lines and see what the slip is
really worth.

Read-only: it works from what the scheduled jobs recorded and never calls
the Odds API. A leg's chance is the model's number blended 30/70 toward the
market's, and legs from the same game are priced with the correlations
measured from history.
"""

import datetime as dt

import pandas as pd
import streamlit as st

from ..betting import correlated
from ..data import nba_stats
from ..tracking import nba_alt, nba_paper, nba_parlay, nba_view
from . import shared


def render() -> None:
    ledger = nba_paper.load_ledger()
    if ledger.empty:
        st.info("No lines recorded yet. The scheduled job fills this in once "
                "tonight's FanDuel lines are posted.")
        return
    st.subheader("Parlay builder")
    st.caption(
        "Every leg here is a **player points** bet: over, under, or X+ points. "
        "Rebounds, assists and other stats aren't projected yet."
    )
    left, right = st.columns(2)
    date = left.selectbox("Slate", nba_view.game_dates(ledger), key="parlay_date")
    versions = sorted(ledger["model_version"].dropna().unique(), reverse=True)
    version = right.selectbox("Model", versions, key="parlay_model")

    candidates = nba_parlay.candidate_legs(ledger, nba_alt.load_ledger(), date, version)
    if candidates.empty:
        st.info("This model didn't price any lines on that slate.")
        return
    _suggested(candidates)
    st.divider()
    _builder(candidates)


def _suggested(candidates: pd.DataFrame) -> None:
    st.markdown("#### Suggested slips")
    slips = nba_parlay.suggest_parlays(candidates)
    if slips.empty:
        st.info("Not enough value on this slate to build a slip: it needs a leg "
                "worth betting on its own in at least two different games.")
        return
    shown = slips.assign(Pays=slips["Pays"].map(lambda x: f"{x:.1f} to 1"))
    st.dataframe(shown, use_container_width=True, hide_index=True, column_config={
        "Chance %": st.column_config.NumberColumn(format="%.1f"),
        "EV %": st.column_config.NumberColumn(format="%+.1f"),
    })
    st.caption("Each leg is worth betting on its own, from a different game, so the "
               "legs are independent. A slip multiplies the chances, so a model that "
               "is a little too confident gets a lot more wrong on a parlay.")


@st.cache_data(ttl=3600, show_spinner=False)
def _teams() -> dict[int, str]:
    """Each player's team from the cached game logs; empty if unavailable."""
    today = dt.date.today()
    try:
        return nba_parlay.player_teams(
            nba_stats.load_season(nba_stats.current_season(today), today=today))
    except nba_stats.NbaDataError:
        return {}


def _builder(candidates: pd.DataFrame) -> None:
    st.markdown("#### Build your own")
    picked = st.multiselect(
        "Legs", list(candidates.index), key="parlay_legs",
        format_func=lambda i: _describe(candidates.loc[i]),
        help="Search by player name. One leg per player.")
    if not picked:
        st.caption("Pick two or more legs to price the slip.")
        return
    chosen = candidates.loc[picked]
    try:
        summary = correlated.summarise(nba_parlay.to_legs(chosen, _teams()))
    except ValueError as error:
        st.error(str(error))
        return

    chance, fair, pays, value = st.columns(4)
    chance.metric("Chance all hit", f"{summary['joint_probability'] * 100:.1f}%")
    fair.metric("Fair odds", shared.fmt_american(summary["fair_american"]))
    pays.metric("Legs multiplied pay", shared.fmt_american(
        correlated.decimal_to_american(summary["decimal_odds"])) if len(picked) > 1
        else shared.fmt_american(chosen["Odds"].iloc[0]))
    value.metric("EV per $1", f"{summary['ev_per_unit']:+.2f}")

    st.dataframe(
        chosen[["Leg", "Stat", "Game", "Odds", "Model %", "Market %", "Blended %", "Leg EV %"]]
        .assign(Odds=lambda t: t["Odds"].map(shared.fmt_american)),
        use_container_width=True, hide_index=True, column_config={
            col: st.column_config.NumberColumn(format="%.1f")
            for col in ("Model %", "Market %", "Blended %")
        } | {"Leg EV %": st.column_config.NumberColumn(format="%+.1f")})
    st.caption(_correlation_note(summary))


def _describe(row: pd.Series) -> str:
    return f"{row['Leg']}  ({shared.fmt_american(row['Odds'])})  ·  {row['Game']}"


def _correlation_note(summary: dict) -> str:
    gap = (summary["joint_probability"] - summary["independent_probability"]) * 100
    return (
        f"Multiplying the legs as if independent gives "
        f"{summary['independent_probability'] * 100:.1f}%; allowing for same-game "
        f"correlation moves it {gap:+.1f} points. Measured over three seasons, "
        "teammates' points move very slightly against each other and opponents' "
        "very slightly together, so for points alone it barely matters. It would "
        "matter a lot for bets tied to the same game total or result, which this "
        "doesn't cover. The payout shown is each leg's price multiplied; FanDuel "
        "prices same-game slips itself and usually pays less, so check its quote "
        "before betting. Untested projections: treat any slip as a paper bet."
    )
