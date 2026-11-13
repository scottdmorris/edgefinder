"""The Record screen's data: every FanDuel pick as locked, how it turned out, and whether the
record has been changed since. Read-only, and built from the functions in `tracking/`.
"""

import datetime as dt
from pathlib import Path

import pandas as pd

from ..tracking import gap_log, nba_alt, nba_paper, nba_record, pick_chain
from . import service

DIGESTS = Path(__file__).resolve().parents[3] / "record" / "DIGESTS.md"
LOG_ROWS = 400                # most recent picks sent to the page; the full ledger is in the repo
BOOKS = (("fanduel", "FanDuel"), ("kalshi", "Kalshi"))


def _time(value) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).isoformat()


def _plain(text: str) -> str:
    """Markdown bold markers out, for a page that styles its own text."""
    return text.replace("**", "")


def chain() -> dict:
    """Is the record tamper-evident and unchanged right now?"""
    path = pick_chain.chain_path_for(nba_paper.LEDGER_PATH)
    verified = pick_chain.verify(path)
    if not verified.entries:
        return {"started": False}
    audit = pick_chain.audit(service.load_ledger(), path)
    checks = pick_chain.check_published(path, DIGESTS)
    return {
        "started": True, "intact": verified.intact, "entries": verified.entries,
        "imported": verified.imported, "first_at": verified.first_at, "head": verified.head,
        "rows": audit.rows, "matched": audit.matched, "clean": audit.clean,
        "published": [{"date": d, "entry": n, "ok": ok} for d, n, ok in checks],
        "problems": (verified.problems + audit.problems)[:5],
    }


def _models(ledger: pd.DataFrame) -> list[dict]:
    out = []
    for version in sorted(ledger["model_version"].dropna().unique(), reverse=True):
        picks = nba_paper.summary(ledger, model_version=version)
        accuracy = nba_paper.calibration_summary(ledger, model_version=version)
        bins = nba_record.calibration_bins(ledger, version)
        out.append({
            "id": version, "name": service.model_name(version),
            "short": service.model_short(version),
            "record": picks["record"], "picks": picks["picks"], "settled": picks["settled"],
            "units": service._num(picks["units"]), "roi_pct": service._num(picks["roi_pct"], 1),
            "verdict": _plain(nba_record.verdict(accuracy["brier_model"],
                                                 accuracy["brier_market"], accuracy["n"])),
            "calibration": [{"bucket": r["Model chance"], "lines": int(r["Lines"]),
                             "model": service._num(r["Model said"], 1),
                             "market": service._num(r["Market said"], 1),
                             "actual": service._num(r["Actually happened"], 1)}
                            for r in bins.to_dict("records")],
        })
    return out


def _gaps() -> dict | None:
    log = gap_log.load()
    if log.empty:
        return None
    s = gap_log.summary(log)
    pick = lambda part: {"logged": s[part].get("logged"), "record": s[part]["record"],  # noqa: E731
                         "units": service._num(s[part]["units"])}
    return {"all": pick("all"), "exact": pick("exact"), "estimated": pick("estimated")}


def _clv(ledger: pd.DataFrame) -> list[dict]:
    summary = nba_record.clv_summary(ledger)
    return [{"book": book, "name": name, "measured": facts["measured"],
             "avg_pct": service._num(facts["avg_clv_pct"], 1),
             "beat_pct": service._num(facts["beat_close_pct"], 0)}
            for book, name in BOOKS
            if (facts := summary.get(book)) and facts["measured"]]


def by_book(ledger: pd.DataFrame) -> list[dict]:
    """Every book's picks split by stat, all models together. Kept apart because a long-shot
    Kalshi ladder and a FanDuel main line are different bets, and mixing them hides both."""
    out = []
    for book, name in BOOKS:
        rows = []
        for stat in sorted(ledger.loc[ledger["book"] == book, "stat"].dropna().unique()):
            s = nba_paper.summary(ledger, stat=stat, book=book)
            if s["settled"]:
                rows.append({"stat": stat, "record": s["record"], "settled": s["settled"],
                             "units": service._num(s["units"]),
                             "roi_pct": service._num(s["roi_pct"], 1)})
        if rows:
            out.append({"book": book, "name": name, "stats": rows})
    return out


def _running(locked: pd.DataFrame) -> list[dict]:
    running = nba_record.cumulative_units(locked)
    return [{"day": r["Game day"], "model": r["Model"], "units": service._num(r["Units"])}
            for r in running.to_dict("records")]


def _days(locked: pd.DataFrame) -> list[dict]:
    daily = nba_record.daily_results(locked)
    return [{"day": r["Game day"], "model": r["Model"], "picks": int(r["Picks"]),
             "graded": int(r["Graded"]), "record": r["Record"], "units": service._num(r["Units"])}
            for r in daily.to_dict("records")]


def _log(locked: pd.DataFrame) -> list[dict]:
    recent = locked.sort_values("Locked", ascending=False).head(LOG_ROWS)
    return [{"day": r["Game day"], "player": r["Player"], "bet": r["Bet"],
             "odds": None if pd.isna(r["Odds"]) else int(r["Odds"]), "model": r["model_version"],
             "locked": _time(r["Locked"]), "lead": nba_record.lead_label(r["Min before tip"]),
             "result": None if pd.isna(r["Result"]) else r["Result"],
             "units": service._num(r["Units"])}
            for r in recent.to_dict("records")]


def record() -> dict:
    def build() -> dict:
        everything = service.load_ledger()
        ledger = nba_paper.scope(everything, book=nba_paper.DEFAULT_BOOK)
        if everything.empty:
            return {"empty": True}
        locked = nba_record.locked_picks(ledger)
        report = nba_record.integrity(ledger)
        alt = nba_alt.summary(service.load_alt())
        return {
            "empty": False,
            "integrity": {"picks": report["picks"], "graded": report["graded"],
                          "after_tip": report["after_tip"],
                          "first_lock": _time(report["first_lock"]),
                          "last_lock": _time(report["last_lock"])},
            "chain": chain(), "clv": _clv(everything), "gaps": _gaps(),
            "by_book": by_book(everything),
            "models": _models(ledger),
            "alt": {"picks": alt["picks"], "settled": alt["settled"], "record": alt["record"]},
            "running": _running(locked), "days": _days(locked), "log": _log(locked),
            "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    return service.cached(("record",), build, 120)
