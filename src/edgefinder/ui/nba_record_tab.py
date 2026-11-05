"""Our record: every pick as it was locked, and how it turned out.

Read-only. The point of the page is that it doesn't ask for trust: it shows
when each pick was locked, counts any that were recorded after tip-off, and
refuses to say the models beat the market until there are enough graded
lines to mean something.
"""

import altair as alt
import pandas as pd
import streamlit as st

from ..tracking import nba_alt, nba_paper, nba_parlay, nba_record
from . import shared, style


def render() -> None:
    ledger = nba_paper.load_fanduel_ledger()
    st.subheader("Our record")
    if ledger.empty:
        st.info("No picks yet. They appear here as soon as the first lines are recorded.")
        return
    st.caption("Every pick is written down before the game and graded after it. Only the "
               "result is filled in later, and the lock time below shows it.")
    locked = nba_record.locked_picks(ledger)
    _status(nba_record.integrity(ledger))
    _models(ledger)
    _profit_chart(locked)
    _calibration(ledger)
    _days(locked)
    _log(locked)


def _status(report: dict) -> None:
    left, middle, right = st.columns(3)
    left.markdown(style.stat_tile("Picks locked", str(report["picks"])), unsafe_allow_html=True)
    middle.markdown(style.stat_tile("Graded so far", str(report["graded"])),
                    unsafe_allow_html=True)
    clean = report["after_tip"] == 0
    right.markdown(style.stat_tile("Recorded after tip-off", str(report["after_tip"]),
                                   style.GREEN if clean else style.RED), unsafe_allow_html=True)
    if report["first_lock"] is not None:
        st.caption(f"First locked {report['first_lock']:%b %d, %I:%M %p} ET · most recent "
                   f"{report['last_lock']:%b %d, %I:%M %p} ET. "
                   + ("Every pick was recorded before its game started."
                      if clean else "Some picks were recorded after tip-off: ignore those."))


def _models(ledger: pd.DataFrame) -> None:
    st.markdown("#### How each model is doing")
    for version in sorted(ledger["model_version"].dropna().unique(), reverse=True):
        picks = nba_paper.summary(ledger, model_version=version)
        accuracy = nba_paper.calibration_summary(ledger, model_version=version)
        st.markdown(f"**{nba_parlay.model_name(version)}**")
        record, units, roi = st.columns(3)
        record.markdown(style.stat_tile("Record", picks["record"]), unsafe_allow_html=True)
        units.markdown(style.stat_tile("Units", f"{picks['units']:+.1f}"), unsafe_allow_html=True)
        roi.markdown(style.stat_tile("Return", f"{picks['roi_pct']:+.0f}%"),
                     unsafe_allow_html=True)
        st.markdown(nba_record.verdict(accuracy["brier_model"], accuracy["brier_market"],
                                       accuracy["n"]))
    alt_picks = nba_alt.summary(nba_alt.load_ledger())
    if alt_picks["picks"]:
        st.caption(f"X+ points picks: {alt_picks['picks']} locked, {alt_picks['settled']} graded, "
                   f"record {alt_picks['record']}.")
    st.caption("A unit is one flat bet. \"Return\" is profit as a share of everything staked. "
               "The verdict compares each model's accuracy to FanDuel's own odds on the same "
               "lines, which is the test that matters.")


def _profit_chart(locked: pd.DataFrame) -> None:
    st.markdown("#### Running profit")
    running = nba_record.cumulative_units(locked)
    if running.empty:
        st.markdown(style.empty_slip(
            "Nothing graded yet",
            "The first results appear the morning after the first games are played."),
            unsafe_allow_html=True)
        return
    running = running.assign(Model=running["Model"].map(nba_parlay.model_name))
    chart = alt.Chart(running).mark_line(point=True, strokeWidth=2.5).encode(
        x=alt.X("Game day:N", title=None), y=alt.Y("Units:Q", title="Units won"),
        color=alt.Color("Model:N", legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["Game day", "Model", alt.Tooltip("Units:Q", format="+.2f")]).properties(height=240)
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        color="#3b4a6b", strokeDash=[4, 4]).encode(y="y:Q")
    st.altair_chart(zero + chart, use_container_width=True)


def _calibration(ledger: pd.DataFrame) -> None:
    st.markdown("#### When it says 60%, does it happen 60% of the time?")
    versions = sorted(ledger["model_version"].dropna().unique(), reverse=True)
    version = style.choose("Model", versions, "record_calibration_model",
                           format_func=nba_parlay.model_name)
    bins = nba_record.calibration_bins(ledger, version)
    if bins.empty:
        st.caption("This fills in once games have been graded. A trustworthy model's "
                   "chances match how often things really happen.")
        return
    melted = bins.melt(id_vars=["Model chance", "Lines"],
                       value_vars=["Model said", "Market said", "Actually happened"],
                       var_name="Who", value_name="Chance")
    chart = alt.Chart(melted).mark_bar().encode(
        x=alt.X("Model chance:N", title="The model's chance of the over", sort=None),
        xOffset="Who:N", y=alt.Y("Chance:Q", title="%", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("Who:N", legend=alt.Legend(orient="bottom", title=None),
                        scale=alt.Scale(domain=["Model said", "Market said", "Actually happened"],
                                        range=["#EFF3F4", "#8B98A5", "#00BA7C"])),
        tooltip=["Model chance", "Who", alt.Tooltip("Chance:Q", format=".1f"), "Lines"],
    ).properties(height=240)
    st.altair_chart(chart, use_container_width=True)
    st.caption("Green bars should match the blue ones. Small groups swing a lot, so ignore "
               "any group with only a few lines.")


def _days(locked: pd.DataFrame) -> None:
    daily = nba_record.daily_results(locked)
    if daily.empty:
        return
    st.markdown("#### Day by day")
    shown = daily.assign(Model=daily["Model"].map(nba_parlay.model_name),
                         Units=daily["Units"].map(lambda u: f"{u:+.2f}"))
    st.dataframe(shown, use_container_width=True, hide_index=True)


def _log(locked: pd.DataFrame) -> None:
    st.markdown("#### Every pick, as locked")
    if locked.empty:
        st.caption("No picks yet.")
        return
    table = pd.DataFrame({
        "Game day": locked["Game day"], "Player": locked["Player"], "Bet": locked["Bet"],
        "Odds": locked["Odds"].map(shared.fmt_american),
        "Model": locked["Model"].map(nba_parlay.model_name),
        "Locked (ET)": locked["Locked"].dt.strftime("%b %d, %I:%M %p"),
        "Lead": locked["Min before tip"].map(nba_record.lead_label),
        "Result": locked["Result"].map({"win": "✅ Win", "loss": "❌ Loss"}).fillna("Pending"),
        "Units": locked["Units"].map(lambda u: "" if pd.isna(u) else f"{u:+.2f}"),
    })
    st.dataframe(table, use_container_width=True, hide_index=True, height=420)
    st.caption("Picks stay on this list win or lose. Players who don't play are graded void "
               "and don't count either way.")
