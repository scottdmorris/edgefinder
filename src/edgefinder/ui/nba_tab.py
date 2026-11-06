"""NBA player points: paper tracking.

Read-only. It shows what the scheduled jobs have written (tonight's lines
with each model's projection, the scorecard, and how much data exists)
and never calls the Odds API, so looking costs no requests.
"""

import datetime as dt

import pandas as pd
import streamlit as st

from ..data import nba_live, nba_props, odds_api
from ..data.nba_snapshot_plan import EASTERN
from ..tracking import nba_paper, nba_parlay, nba_view
from . import nba_alt_tab, nba_parlay_tab, shared, style, team_colors

GAP_SORT = "Biggest gap between projection and line"
GAME_SORT = "Game"


def render() -> None:
    st.subheader("Model picks")
    ledger = nba_paper.load_fanduel_ledger()
    if ledger.empty:
        st.info(
            "No lines recorded yet. The scheduled job fills this in once "
            "tonight's FanDuel lines are posted, or run "
            "`scripts/nba_props_snapshot.py` by hand."
        )
        return
    st.caption("Paper only: no money is staked. The question is whether any model beats "
               "FanDuel's own odds over many bets, not whether one pick looks good.")
    _suggestions(ledger)
    st.divider()
    nba_alt_tab.render(ledger)
    st.divider()
    _tonights_lines(ledger)
    st.divider()
    _scorecard(ledger)
    st.divider()
    _collection(ledger)


def _day(game_date: str) -> str:
    return nba_view.day_label(game_date, dt.datetime.now(EASTERN).date())


def _suggestions(ledger: pd.DataFrame) -> None:
    st.markdown("#### Bets the models like")
    date = style.choose("Game day", nba_view.game_dates(ledger), "nba_suggest_date",
                        format_func=_day)
    table = nba_view.suggestions(ledger, date)
    if table.empty:
        st.info("No model sees positive expected value on this day.")
        return
    st.markdown(style.notice(
        "Not proven yet: only a few nights are graded (see Record). A projection far from the "
        "line usually means the model is missing news, not that it found an edge."),
        unsafe_allow_html=True)
    teams = nba_parlay_tab.teams_by_player()
    left, right = st.columns(2)
    for position, pick in enumerate(table.to_dict("records")):
        team = teams.get(pick["player_id"], "")
        player, wager = pick["Bet"].split(" · ", 1)
        agree = "both models" if pick["Agree"] > 1 else "one model"
        (left if position % 2 == 0 else right).markdown(style.leg_card(
            nba_parlay.headshot_url(pick["player_id"]), player, f"{wager}  ·  {nba_view.short_game(pick['Game'])}",
            shared.fmt_american(pick["Odds"]), compact=True,
            detail=f"Model projects {pick['Model projects']:.1f}  ·  "
                   f"edge {pick['EV %']:+.1f}%  ·  {agree}",
            accent=team_colors.team_color(team) if team else "",
            logo=nba_live.logo_url(team) if team else ""), unsafe_allow_html=True)


def _tonights_lines(ledger: pd.DataFrame) -> None:
    st.markdown("#### Every line, with both projections")
    date = style.choose("Game day", nba_view.game_dates(ledger), "nba_lines_date",
                        format_func=_day)
    middle, right = st.columns([2, 2])
    sort = middle.radio("Sort by", [GAP_SORT, GAME_SORT], horizontal=True)
    picks_only = right.checkbox("Only lines where a model picks a side", value=False)

    table = nba_view.lines_for_date(ledger, date)
    pick_columns = [c for c in table.columns if c.endswith(" pick")]
    if picks_only:
        table = table[(table[pick_columns] != "").any(axis=1)]
    if sort == GAP_SORT:
        table = table.reindex(table["Gap"].abs().sort_values(ascending=False).index)
    if table.empty:
        st.info("No lines match.")
        return

    shown = _for_display(table)
    st.dataframe(shown, use_container_width=True, hide_index=True,
                 column_config=_column_config(shown))
    st.caption(
        "**Gap** is the newest model's projection minus the line: positive "
        "means it expects more points than FanDuel does. **over %** is each "
        "model's probability of the over; **Market over %** is FanDuel's own "
        "price with the vig removed. A **pick** means the model, blended 30/70 "
        "with the market, sees at least 2% expected value on that side. "
        "Treat a pick as a test of the model, not a recommendation: most big "
        "gaps are things the model can't see, like who is injured tonight."
    )


def _for_display(table: pd.DataFrame) -> pd.DataFrame:
    shown = table.copy()
    for column in shown.columns:
        if column.endswith("P(over)"):
            shown[column] = shown[column] * 100.0
    shown["Over odds"] = shown["Over odds"].map(shared.fmt_american)
    shown["Under odds"] = shown["Under odds"].map(shared.fmt_american)
    return shown.rename(columns=lambda c: c.replace("P(over)", "over %"))


def _column_config(shown: pd.DataFrame) -> dict:
    config = {
        "Line": st.column_config.NumberColumn(format="%.1f"),
        "Gap": st.column_config.NumberColumn(
            format="%+.1f", help="Newest model's projection minus the line"),
    }
    for column in shown.columns:
        if column.endswith(" proj"):
            config[column] = st.column_config.NumberColumn(format="%.1f")
        elif column.endswith("over %"):
            config[column] = st.column_config.NumberColumn(format="%.0f")
    return config


def _scorecard(ledger: pd.DataFrame) -> None:
    st.markdown("#### Scorecard")
    settled = int((ledger["status"] == "settled").sum())
    if settled == 0:
        st.info(
            "Nothing has settled yet. The morning job grades each night's "
            "games, so the first results appear the day after the first "
            "lines were recorded, and a few weeks of games are needed before "
            "any comparison means much."
        )
        return
    st.dataframe(nba_view.scorecard(ledger), use_container_width=True,
                 column_config={
                     "Units": st.column_config.NumberColumn(format="%+.2f"),
                     "ROI %": st.column_config.NumberColumn(format="%+.1f"),
                     "Avg CLV %": st.column_config.NumberColumn(format="%+.2f"),
                     "Model Brier": st.column_config.NumberColumn(format="%.4f"),
                     "Market Brier": st.column_config.NumberColumn(format="%.4f"),
                 })
    head_to_head = nba_paper.compare_versions(ledger)
    if not head_to_head.empty:
        st.markdown("**Head to head** on only the lines every model priced")
        st.dataframe(head_to_head, use_container_width=True, column_config={
            "brier_model": st.column_config.NumberColumn("Model Brier", format="%.4f"),
            "brier_market": st.column_config.NumberColumn("Market Brier", format="%.4f"),
        })
    st.caption(
        "**Brier score** measures how far each probability was from what "
        "actually happened, so lower is better. A model only has something "
        "to offer if its Brier beats the market's on the same lines. "
        "**CLV** is how the line moved after the pick."
    )


def _collection(ledger: pd.DataFrame) -> None:
    st.markdown("#### Data collected")
    status = nba_view.collection_status(nba_props.load_snapshots(), ledger)
    quota = odds_api.get_quota()
    games, archived, rows, settled, remaining = st.columns(5)
    games.metric("Games snapshotted", status["games"])
    archived.metric("Lines archived", status["lines_archived"])
    rows.metric("Ledger rows", status["ledger_rows"])
    settled.metric("Settled", status["settled"])
    remaining.metric("Odds requests left", quota["remaining"] if quota else "—")
    st.caption(
        "A scheduled job snapshots FanDuel's player-points lines every 30 "
        "minutes between noon and 10:30 pm ET (at most 6 games a night, one "
        "early price and one near tip-off) and grades the night before at "
        f"9 am. Last snapshot: {status['last_snapshot'] or 'none yet'}."
    )
