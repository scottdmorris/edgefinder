"""X+ points bets ("Jaylen Brown 15+"): a ladder for any player, and the
suggested X+ bets from FanDuel's real prices once they've been recorded.

Read-only. It never calls the Odds API.
"""

import datetime as dt

import pandas as pd
import streamlit as st

from ..data.nba_snapshot_plan import EASTERN
from ..tracking import nba_alt, nba_view
from . import shared, style


def render(ledger: pd.DataFrame) -> None:
    st.markdown("#### X+ points: chance of a player reaching a total")
    date = style.choose("Game day", nba_view.game_dates(ledger), "nba_alt_date",
                        format_func=lambda d: nba_view.day_label(
                            d, dt.datetime.now(EASTERN).date()))
    players = sorted(ledger.loc[ledger["game_date"] == date, "player"].unique())
    player = st.selectbox("Player", players, key="nba_alt_player",
                          help="Type to search.")
    table = nba_alt.ladder(nba_alt.player_means(ledger, date, player))
    st.dataframe(_display(table), use_container_width=True, hide_index=True,
                 column_config=_config(table))
    st.caption(
        "Each model's chance that the player scores at least that many, and "
        "the odds that would break even. If FanDuel pays better than the fair "
        "odds, the model thinks it's value. Compare it with the price in the "
        "FanDuel app. These need a projection, so only players FanDuel posts "
        "a points line for are listed."
    )
    _suggested(date)


def _suggested(date: str) -> None:
    st.markdown("#### Suggested X+ bets (paper only)")
    table = nba_alt.suggestions(nba_alt.load_ledger(), date)
    if table.empty:
        st.info(
            "No X+ prices recorded with value on this slate. They are pulled "
            "from FanDuel at each game's early snapshot, for up to four games a "
            "night, starting with the next snapshot."
        )
        return
    shown = table.assign(Odds=table["Odds"].map(shared.fmt_american))
    st.dataframe(shown, use_container_width=True, hide_index=True, column_config={
        "Model projects": st.column_config.NumberColumn(format="%.1f"),
        "Model chance %": st.column_config.NumberColumn(format="%.0f"),
        "EV %": st.column_config.NumberColumn(format="%+.1f"),
        "Agree": st.column_config.NumberColumn(help="How many models pick this price"),
    })
    st.caption(
        "Not proven yet, like the other suggestions. X+ prices have no under side, so "
        "the market's own number includes the book's cut and the model has to "
        "clear that to show up here."
    )


def _display(table: pd.DataFrame) -> pd.DataFrame:
    shown = table.copy()
    for column in shown.columns:
        if column.endswith("fair odds"):
            shown[column] = shown[column].map(shared.fmt_american)
    return shown


def _config(table: pd.DataFrame) -> dict:
    return {column: st.column_config.NumberColumn(format="%.0f")
            for column in table.columns if column.endswith("chance %")}
