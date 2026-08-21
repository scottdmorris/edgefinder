"""Bet Log: P/L, ROI, closing-line value, and the paper-trade record."""

import pandas as pd
import streamlit as st

from ..tracking import bet_log, paper
from . import shared


def render() -> None:
    st.subheader("Bet Log")
    _paper_section()
    st.divider()
    st.markdown("### Your real bets")
    df = bet_log.load_log()
    if df.empty:
        st.info("No bets logged yet. Log bets from the Evaluator or Parlay tabs.")
        return
    stats = bet_log.summary(df)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Bets placed", stats["bets_placed"])
    col2.metric("Net P/L", f"${stats['net_pnl']:,.2f}")
    col3.metric("ROI", f"{stats['roi_pct']:.1f}%")
    clv = stats["avg_clv_pct"]
    col4.metric("Avg CLV", "—" if clv is None else f"{clv:+.2f}%")
    st.caption(
        "CLV (closing line value) is whether you beat the closing price. "
        "Sustained positive CLV is the real evidence of an edge; short-term "
        "win/loss is mostly noise."
    )
    st.dataframe(df, use_container_width=True)
    _settle_form(df)
    st.download_button(
        "⬇️ Download log as CSV", df.to_csv(index=False),
        file_name="bet_log.csv", mime="text/csv",
    )


def _paper_section() -> None:
    """The model's own track record: auto-recorded picks, auto-settled
    from final scores, flat 1-unit stakes."""
    st.markdown("### 🧪 Model track record (paper trades, no money)")
    season, today_iso = shared.current_season_and_date()
    settled_now = paper.settle_pending(season)
    if settled_now:
        st.toast(f"Auto-settled {settled_now} paper pick(s) from final scores.")
    record_col, _ = st.columns([1, 2])
    if record_col.button("📌 Record today's +EV picks"):
        board = shared.cached_board(season, today_iso)
        added = paper.record_board_picks(board, today_iso)
        if added:
            st.success(f"Recorded {added} pick(s) for {today_iso}.")
        else:
            st.info("Nothing new to record (no clean +EV picks, or "
                    "already recorded today).")
    df = paper.load_log()
    if df.empty:
        st.caption(
            "No paper picks yet. Record picks daily and after ~100 the "
            "ROI and CLV here tell you whether the model truly beats "
            "FanDuel — before real money rides on it."
        )
        return
    stats = paper.summary(df)
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Picks", stats["picks"])
    col2.metric("Record", stats["record"])
    col3.metric("Units", f"{stats['units']:+.2f}")
    col4.metric("ROI", f"{stats['roi_pct']:+.1f}%")
    clv = stats["avg_clv_pct"]
    col5.metric("Avg CLV", "—" if clv is None else f"{clv:+.2f}%")
    with st.expander("All paper picks"):
        st.dataframe(df, use_container_width=True)


def _settle_form(df: pd.DataFrame) -> None:
    pending = df[df["result"] == "pending"]
    if pending.empty:
        return
    st.markdown("**Settle a pending bet**")
    options = [f"{i}: {row['description']}" for i, row in pending.iterrows()]
    choice = st.selectbox("Bet", options)
    index = int(choice.split(":")[0])
    result = st.selectbox("Result", ["win", "loss", "push"])
    closing = st.number_input(
        "Closing odds (American, 0 = unknown)", value=0, step=5,
        help="The line just before game start. Used to compute CLV.",
    )
    if st.button("Settle bet"):
        bet_log.settle_bet(index, result, closing if closing != 0 else None)
        st.success("Settled.")
        st.rerun()
