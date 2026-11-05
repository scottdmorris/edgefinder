"""Parlay builder: pick bets from the day's lines and see what the slip is
really worth.

Read-only: it works from what the scheduled jobs recorded and never calls
the Odds API. A bet's chance is the model's number blended 30/70 toward the
market's, and bets from the same game are priced with the correlations
measured from history.
"""

import datetime as dt

import altair as alt
import pandas as pd
import streamlit as st

from ..betting import correlated
from ..data import nba_stats
from ..tracking import nba_alt, nba_paper, nba_parlay, nba_view
from . import shared, style

DEFAULT_STAKE = 10.0
LEGS_KEY = "parlay_legs"
HOW_TO = (
    "**1.** Pick a game day and a projection.  **2.** Add bets (called legs): "
    "a player to go over or under a points line, or to score a number or more.  "
    "**3.** Read the box: how likely it is that every bet hits, and whether the "
    "payout is worth that risk."
)
GLOSSARY = """
- **Parlay / slip:** several bets tied together. Every one has to hit to get paid.
- **Leg:** one bet inside the parlay.
- **Over 24.5 points:** the player scores 25 or more. **25+ points** is the same idea.
- **Chance it hits:** how likely the model thinks it is. *1 in 37* is the same number
  said another way.
- **Odds that break even:** the payout at which the bet is a coin flip between
  winning and losing money over time. If the book pays more than that, the bet has
  value; if it pays less, it doesn't.
- **Expected profit per \\$1:** what you'd win or lose on average per dollar if you
  made this exact bet again and again, *assuming the model is right*. Long shots
  can show big expected profits while still almost never hitting.
- **Average result at this stake:** the same number scaled to what you typed in.
  It is an average over many repeats, not what happens on one bet.
- **Projection:** the model's guess at how many points a player scores. Neither
  projection has been tested against real results yet.
"""


def render() -> None:
    ledger = nba_paper.load_ledger()
    if ledger.empty:
        st.info("No lines recorded yet. The scheduled job fills this in once "
                "tonight's FanDuel lines are posted.")
        return
    st.subheader("Parlay builder")
    st.markdown(HOW_TO)
    st.caption("Every bet here is a **player points** bet. Rebounds, assists and "
               "other stats aren't projected yet.")
    with st.expander("What do these words mean?"):
        st.markdown(GLOSSARY)

    left, right = st.columns(2)
    date = left.selectbox("Game day", nba_view.game_dates(ledger), key="parlay_date",
                          on_change=_clear_slip)
    versions = sorted(ledger["model_version"].dropna().unique(), reverse=True)
    version = right.selectbox("Projection", versions, key="parlay_model",
                              format_func=nba_parlay.model_name, on_change=_clear_slip)

    candidates = nba_parlay.candidate_legs(ledger, nba_alt.load_ledger(), date, version)
    if candidates.empty:
        st.info("This projection didn't price any lines on that day.")
        return
    _suggested(candidates)
    st.divider()
    _browse(candidates)
    st.divider()
    _builder(candidates)


def _clear_slip() -> None:
    """Bets are positions in the day's table, so they mean nothing after the
    day or projection changes."""
    st.session_state[LEGS_KEY] = []


def _toggle(index: int, candidates: pd.DataFrame) -> None:
    st.session_state[LEGS_KEY] = nba_parlay.toggle_leg(
        list(st.session_state.get(LEGS_KEY, [])), index, candidates["player_id"])


def _browse(candidates: pd.DataFrame) -> None:
    st.markdown("#### Add bets")
    games = list(dict.fromkeys(candidates["Game"]))
    game = st.selectbox("Pick a game", games, key="browse_game")
    day = candidates[candidates["Game"] == game]
    slip = set(st.session_state.get(LEGS_KEY, []))
    stars_first = day.groupby("player_id")["line"].max().sort_values(ascending=False).index
    st.caption("Tap a price to add it to your slip, tap again to remove it. "
               "**O** is over, **U** is under, and **X+** has more totals.")
    with st.container(height=460):
        for player_id in stars_first:
            _player_row(day[day["player_id"] == player_id], slip, candidates)
    if slip and st.button("Clear my slip", key="clear_slip"):
        _clear_slip()
        st.rerun()


def _player_row(rows: pd.DataFrame, slip: set, candidates: pd.DataFrame) -> None:
    photo, name, over, under, more = st.columns([1, 3, 2, 2, 2], vertical_alignment="center")
    first = rows.iloc[0]
    photo.image(nba_parlay.headshot_url(first["player_id"]), width=44)
    name.markdown(f"**{first['Player']}**")
    main = rows[rows["Side"].isin(["Over", "Under"])]
    for column, side in ((over, "Over"), (under, "Under")):
        match = main[main["Side"] == side]
        if match.empty:
            continue
        _price_button(column, match.index[0], match.iloc[0], slip, candidates,
                      f"{side[0]} {match.iloc[0]['line']:g}")
    totals = rows[~rows["Side"].isin(["Over", "Under"])].sort_values("line")
    if totals.empty:
        return
    with more.popover("X+", use_container_width=True):
        for index, row in totals.iterrows():
            _price_button(st, index, row, slip, candidates, f"{int(row['line'] + 0.5)}+")


def _price_button(container, index: int, row: pd.Series, slip: set, candidates: pd.DataFrame,
                  label: str) -> None:
    container.button(
        f"{label}  {shared.fmt_american(row['Odds'])}", key=f"add_{index}",
        type="primary" if index in slip else "secondary", use_container_width=True,
        on_click=_toggle, args=(index, candidates))


def selected_legs() -> pd.DataFrame | None:
    """The bets currently picked in the builder, for other views to track.
    None when nothing is picked or the lines aren't available."""
    picked = st.session_state.get("parlay_legs")
    date, version = st.session_state.get("parlay_date"), st.session_state.get("parlay_model")
    ledger = nba_paper.load_ledger()
    if not picked or date is None or version is None or ledger.empty:
        return None
    candidates = nba_parlay.candidate_legs(ledger, nba_alt.load_ledger(), date, version)
    chosen = candidates.reindex(picked).dropna(subset=["Leg"])
    return None if chosen.empty else chosen


def _suggested(candidates: pd.DataFrame) -> None:
    st.markdown("#### Ideas the model likes")
    slips = nba_parlay.suggest_parlays(candidates)
    if slips.empty:
        st.info("Nothing to suggest on this day: it takes a bet worth making on its "
                "own in at least two different games.")
        return
    shown = pd.DataFrame({
        "Bets": slips["Slip"].str.replace("  +  ", "  +  ", regex=False),
        "Chance it hits": [f"{c:.1f}%  ({nba_parlay.one_in(c / 100)})" for c in slips["Chance %"]],
        "$1 pays": [f"${p + 1:,.2f}" for p in slips["Pays"]],
        "Expected profit per $1": [f"{e / 100:+.2f}" for e in slips["EV %"]],
    })
    st.dataframe(shown, use_container_width=True, hide_index=True)
    st.caption(
        "Long shots rank high because the payout is big, not because they're likely: "
        "read **Chance it hits** first. Each bet is worth making on its own and comes "
        "from a different game. A parlay multiplies the chances, so a model that's a "
        "little too confident gets a lot more wrong here."
    )


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
    st.markdown("#### Your slip")
    picked = st.multiselect(
        "Or search for a bet", list(candidates.index), key=LEGS_KEY,
        format_func=lambda i: _describe(candidates.loc[i]),
        help="Type a player's name to search. One bet per player.")
    if not picked:
        st.caption("Add two or more bets to price the parlay.")
        return
    chosen = candidates.loc[picked]
    try:
        summary = correlated.summarise(nba_parlay.to_legs(chosen, _teams()))
    except ValueError as error:
        st.error(str(error))
        return

    _slip_cards(chosen)
    stake = _stake_input()
    _slip_box(summary, chosen, stake)
    _result(summary, chosen)
    _chance_chart(chosen, summary)
    with st.expander("See the numbers behind each bet"):
        _leg_table(chosen)
    st.caption(_correlation_note(summary))


def _slip_cards(chosen: pd.DataFrame) -> None:
    kind = "single bet" if len(chosen) == 1 else f"{len(chosen)}-leg parlay"
    st.markdown(f"**Your bet slip** · {kind}")
    for bet in chosen.itertuples():
        wager = bet.Leg.split(" · ", 1)[1]
        st.markdown(
            style.leg_card(nba_parlay.headshot_url(bet.player_id), bet.Player,
                           f"{wager}  ·  {bet.Game}", shared.fmt_american(bet.Odds)),
            unsafe_allow_html=True)


def _stake_input() -> float:
    return st.number_input(
        "How much are you betting? ($)", min_value=0.0, value=DEFAULT_STAKE, step=5.0,
        format="%.2f", key="stake",
        help="Only used to show dollars. Nothing is placed, and nothing is saved.")


def _slip_box(summary: dict, chosen: pd.DataFrame, stake: float) -> None:
    result = nba_parlay.stake_outcomes(stake, summary["decimal_odds"], summary["ev_per_unit"])
    p = summary["joint_probability"]
    st.markdown(style.slip_summary(
        "PARLAY" if len(chosen) > 1 else "SINGLE BET",
        f"To win {nba_parlay.money(result['profit_if_wins'])}",
        [("Stake", nba_parlay.money(stake)),
         ("Total return", nba_parlay.money(result["total_return"])),
         ("Chance it hits", f"{p * 100:.1f}%  ({nba_parlay.one_in(p)})"),
         ("Average result at this stake",
          nba_parlay.money(result["expected_profit"], signed=True))]),
        unsafe_allow_html=True)


def _result(summary: dict, chosen: pd.DataFrame) -> None:
    chance, fair, pays, value = st.columns(4)
    p = summary["joint_probability"]
    chance.metric("Chance every bet hits", f"{p * 100:.1f}%")
    fair.metric("Odds that break even", shared.fmt_american(summary["fair_american"]))
    payout = (correlated.decimal_to_american(summary["decimal_odds"])
              if len(chosen) > 1 else chosen["Odds"].iloc[0])
    pays.metric("Payout if the odds multiply", shared.fmt_american(payout))
    value.metric("Expected profit per $1", f"{summary['ev_per_unit']:+.2f}")
    st.markdown(
        f"**About {nba_parlay.one_in(p)} to hit, and \\${summary['decimal_odds']:,.2f} comes "
        f"back on every \\$1 if it does.** {nba_parlay.verdict(summary['ev_per_unit'])}")


def _chance_chart(chosen: pd.DataFrame, summary: dict) -> None:
    """Each bet's chance, then the chance they all hit: shows how fast a parlay shrinks."""
    bars = pd.DataFrame({
        "Bet": list(chosen["Leg"]) + ["ALL BETS HIT"],
        "Chance %": list(chosen["Blended %"]) + [summary["joint_probability"] * 100.0],
        "Kind": ["One bet"] * len(chosen) + ["The parlay"],
    })
    chart = alt.Chart(bars).mark_bar().encode(
        x=alt.X("Chance %:Q", scale=alt.Scale(domain=[0, 100]), title="Chance it hits (%)"),
        y=alt.Y("Bet:N", sort=None, title=None,
                axis=alt.Axis(labelLimit=420, labelOverlap=False)),
        color=alt.Color("Kind:N", legend=None,
                        scale=alt.Scale(domain=["One bet", "The parlay"],
                                        range=["#5b8def", "#f2994a"])),
        tooltip=["Bet", alt.Tooltip("Chance %:Q", format=".1f")],
    ).properties(height=max(150, 44 * len(bars)))
    st.altair_chart(chart, use_container_width=True)


def _leg_table(chosen: pd.DataFrame) -> None:
    table = chosen.assign(
        Photo=[nba_parlay.headshot_url(pid) for pid in chosen["player_id"]],
        Odds=chosen["Odds"].map(shared.fmt_american),
    )[["Photo", "Leg", "Game", "Odds", "Model %", "Market %", "Blended %", "Leg EV %"]]
    st.dataframe(
        table.rename(columns={
            "Model %": "Model chance %", "Market %": "FanDuel's chance %",
            "Blended %": "Used here %", "Leg EV %": "Profit per $1 (%)"}),
        use_container_width=True, hide_index=True, row_height=48, column_config={
            "Photo": st.column_config.ImageColumn(" ", width="small"),
            "Model chance %": st.column_config.NumberColumn(format="%.1f"),
            "FanDuel's chance %": st.column_config.NumberColumn(format="%.1f"),
            "Used here %": st.column_config.NumberColumn(
                format="%.1f", help="The model's chance blended 30/70 toward FanDuel's, "
                                    "since the raw model is overconfident."),
            "Profit per $1 (%)": st.column_config.NumberColumn(format="%+.1f"),
        })


def _describe(row: pd.Series) -> str:
    return f"{row['Leg']}  ({shared.fmt_american(row['Odds'])})  ·  {row['Game']}"


def _correlation_note(summary: dict) -> str:
    gap = (summary["joint_probability"] - summary["independent_probability"]) * 100
    return (
        f"Multiplying the bets as if they were unrelated gives "
        f"{summary['independent_probability'] * 100:.1f}%; allowing for bets from the "
        f"same game moves it {gap:+.1f} points. Over three seasons, teammates' points "
        "moved very slightly against each other and opponents' very slightly together, "
        "so for points alone it barely matters. It would matter a lot for bets tied to "
        "the same game's total or result, which this doesn't cover. The payout shown is "
        "each bet's price multiplied; FanDuel prices same-game parlays itself and "
        "usually pays less, so check its quote before betting."
    )
