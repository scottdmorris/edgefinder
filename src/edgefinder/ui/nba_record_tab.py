"""Our record: every pick as it was locked, and how it turned out.

Read-only. The point of the page is that it doesn't ask for trust: it shows
when each pick was locked, counts any that were recorded after tip-off, and
refuses to say the models beat the market until there are enough graded
lines to mean something.
"""

import datetime as dt
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from ..data.nba_snapshot_plan import EASTERN
from ..tracking import nba_alt, nba_paper, nba_parlay, nba_record, pick_chain
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
    _chain_status()
    _closing_value(nba_paper.load_ledger())
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


DIGESTS = Path(__file__).resolve().parents[3] / "record" / "DIGESTS.md"


def _chain_status() -> None:
    """Is the record tamper-evident right now? Walks the chain and compares it to the ledger."""
    chain = pick_chain.chain_path_for(nba_paper.LEDGER_PATH)
    verified = pick_chain.verify(chain)
    if not verified.entries:
        st.caption("The tamper-evident log starts with the next recorded pick.")
        return
    audit = pick_chain.audit(nba_paper.load_ledger(), chain)
    sound = verified.intact and audit.clean
    st.markdown("#### Has anything been changed?")
    chained, rows, head = st.columns(3)
    chained.markdown(style.stat_tile("Log", "Intact" if verified.intact else "BROKEN",
                                     style.GREEN if verified.intact else style.RED),
                     unsafe_allow_html=True)
    rows.markdown(style.stat_tile("Rows matching the log", f"{audit.matched} of {audit.rows}",
                                  style.GREEN if audit.clean else style.RED),
                  unsafe_allow_html=True)
    head.markdown(style.stat_tile("Latest fingerprint", verified.head[:10]),
                  unsafe_allow_html=True)
    began = dt.datetime.fromisoformat(verified.first_at).astimezone(EASTERN)
    st.caption(
        f"Every pick and result is written to an append-only log where each entry carries a "
        f"fingerprint of the one before it, so changing the past breaks everything after. "
        f"{verified.imported} entries were imported when the log began ({began:%b %d}); the "
        f"rest were logged as they happened.")
    checks = pick_chain.check_published(chain, DIGESTS)
    if not checks:
        st.caption("No fingerprint has been published yet. Until one is, this log proves "
                   "nothing to an outsider, since whoever runs it could rebuild it.")
    elif all(ok for _, _, ok in checks):
        date, count, _ = checks[-1]
        st.caption(f"{len(checks)} published fingerprint{'s' if len(checks) != 1 else ''}, "
                   f"the latest from {date} (entry {count}), still match this log.")
    else:
        st.warning("A published fingerprint does NOT match this log: it has been changed or "
                   "cut short since it was published.")
    for problem in (verified.problems + audit.problems)[:5]:
        st.warning(problem)
    if not sound:
        st.warning("The record does not match its log. Do not trust the numbers above.")


def _closing_value(ledger: pd.DataFrame) -> None:
    """The quickest honest read on whether a model has an edge: did the market move our way
    after we picked? Shown per price source, from the first graded picks."""
    st.markdown("#### Did the price move our way?")
    summary = nba_record.clv_summary(ledger)
    shown = False
    for book, label in (("fanduel", "FanDuel"), ("kalshi", "Kalshi")):
        facts = summary.get(book)
        if not facts or not facts["measured"]:
            continue
        shown = True
        st.markdown(f"**{label}**")
        average, beat, count = st.columns(3)
        average.markdown(style.stat_tile("Average move", f"{facts['avg_clv_pct']:+.1f}%"),
                         unsafe_allow_html=True)
        beat.markdown(style.stat_tile("Picks that beat the close",
                                      f"{facts['beat_close_pct']:.0f}%"), unsafe_allow_html=True)
        count.markdown(style.stat_tile("Picks measured", str(facts["measured"])),
                       unsafe_allow_html=True)
    if not shown:
        st.caption("This appears after the first graded picks that have a closing price.")
    st.caption("Closing-line value compares the price we took with the price just before "
               "tip-off. If the market keeps moving our way, we saw something early, and that "
               "shows up long before wins and losses can be trusted.")


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
        color=alt.Color("Model:N", legend=alt.Legend(orient="bottom", title=None),
                        scale=alt.Scale(range=["#EFF3F4", "#8B98A5", "#F5B83D"])),
        tooltip=["Game day", "Model", alt.Tooltip("Units:Q", format="+.2f")]).properties(height=240)
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        color="#536471", strokeDash=[4, 4]).encode(y="y:Q")
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
    st.caption("Green bars should match the white ones. Small groups swing a lot, so ignore "
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
