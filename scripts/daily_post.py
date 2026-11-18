"""Make the morning's X post: a record card (PNG) and a caption, for the last graded night.

The card leads with one fixed model, the app's default (Sharpest), so the headline is never
the night's luckiest model, and lists all four beneath it, wins and losses alike. It is drawn
as HTML in the app's colours and saved as a PNG by Microsoft Edge running headless, which
every Windows 11 PC has. Files land in data/posts/ (git-ignored) as <day>.png and <day>.txt.
Nothing is posted: you post them.

Usage:  python scripts/daily_post.py [--day YYYY-MM-DD]
"""

import argparse
import base64
import datetime as dt
import html
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from string import Template

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from edgefinder.tracking import nba_paper, suggested_record  # noqa: E402

POSTS = ROOT / "data" / "posts"
DIGESTS = ROOT / "record" / "DIGESTS.md"
LOGO = ROOT / "assets" / "logo.svg"
HANDLE = "@BalllKnowledge"
VERIFY_URL = "github.com/scottdmorris/edgefinder"
LEAD_MODEL = "context-v2"
MODELS = {"context-v2": "Sharpest", "context-v1": "Smartest", "minutes-v1": "Smarter", "ewma-v1": "Simple"}
WIDTH, HEIGHT = 1200, 675          # 16:9, how X shows a single image; rendered at 2x
EDGE_PATHS = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
              Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]
RENDER_TIMEOUT_SECONDS = 90
MAX_CAPTION = 280


# ---- the numbers ------------------------------------------------------------------------------

def graded_picks(ledger: pd.DataFrame) -> pd.DataFrame:
    """FanDuel points picks with a result: the same picks the README table counts."""
    return ledger[(ledger["book"] == "fanduel") & (ledger["stat"] == "points")
                  & (ledger["status"] == "settled") & ledger["pick_side"].notna()
                  & ledger["result"].isin(["win", "loss"])]


def tally(picks: pd.DataFrame) -> dict:
    wins, losses = int((picks["result"] == "win").sum()), int((picks["result"] == "loss").sum())
    clv = pd.to_numeric(picks["clv_pct"], errors="coerce").dropna()
    return {"wins": wins, "losses": losses,
            "units": float(pd.to_numeric(picks["pnl_units"], errors="coerce").sum()),
            "beat_close": float((clv > 0).mean() * 100) if len(clv) else None}


def facts(ledger: pd.DataFrame, day: str | None = None) -> dict | None:
    """Last night and the season so far, per model. None when nothing is graded."""
    picks = graded_picks(ledger)
    if picks.empty:
        return None
    dates = picks["game_date"].astype(str)
    day = day or dates.max()
    if day not in set(dates):
        return None
    season = picks[dates <= day]
    night = picks[dates == day]
    models = [{"id": m, "name": MODELS.get(m, m), "night": tally(night[night["model_version"] == m]),
               "season": tally(season[season["model_version"] == m])}
              for m in MODELS if (season["model_version"] == m).any()]
    lead = next((m for m in models if m["id"] == LEAD_MODEL), models[0])
    return {"day": day, "first_day": str(season["game_date"].astype(str).min()),
            "days": int(season["game_date"].nunique()), "models": models, "lead": lead}


def fingerprint(path: Path = DIGESTS) -> str | None:
    """The latest published fingerprint (the last table row's hash), or None."""
    if not path.exists():
        return None
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("| 20")]
    return rows[-1].split("`")[1] if rows and "`" in rows[-1] else None


def trial_slips(day: str, path: Path | None = None) -> list[dict]:
    """The paper trials' graded slips for `day`: name, legs, legs hit, payout and result."""
    db_path = path or suggested_record.DB_PATH
    if not db_path.exists():
        return []
    names = {suggested_record.EXPERIMENT["id"]: "Higher hit rate",
             suggested_record.LONG_SHOT_EXPERIMENT["id"]: "Long shot"}
    out = []
    try:
        with suggested_record.connect(db_path) as db:
            for trial, payload, result in db.execute(
                    "SELECT e.trial, o.payload, o.result FROM experiment e JOIN offers o ON o.id = e.offer "
                    "WHERE e.day = ? AND o.result IS NOT NULL", (day,)):
                slip, graded = json.loads(payload), json.loads(result)
                if graded["status"] == "void":
                    continue
                out.append({"name": names.get(trial, trial), "legs": len(slip["legs"]),
                            "hit": sum(s == "win" for s in graded["legs"]),
                            "payout": float(slip["payout"]), "won": graded["status"] == "win"})
    except sqlite3.Error:
        return []
    return out


# ---- words ------------------------------------------------------------------------------------

def short_date(day: str, weekday: bool = False) -> str:
    """'Nov 16', or 'Sun, Nov 16' with the weekday."""
    date = dt.date.fromisoformat(day)
    return date.strftime("%a, %b " if weekday else "%b ") + str(date.day)


def units_text(units: float) -> str:
    return f"{units:+.2f}u".replace("-", "−")


def record_text(t: dict) -> str:
    return f"{t['wins']}-{t['losses']}"


def american(decimal: float) -> str:
    return f"+{(decimal - 1) * 100:,.0f}" if decimal >= 2 else f"−{100 / (decimal - 1):,.0f}"


def night_line(t: dict) -> str:
    """'5-3 last night, +1.45u 📈': the result first, the way people scan a feed."""
    if not t["wins"] + t["losses"]:
        return "No graded picks last night"
    trend = " 📈" if t["units"] > 0 else " 📉" if t["units"] < 0 else ""
    return f"{record_text(t)} last night, {units_text(t['units'])}{trend}"


def caption(f: dict) -> str:
    """The post text: the result, the season with its losses, a reason to come back, and the
    disclaimer. Kept under X's 280 characters; the proof link goes in the reply."""
    lead = f["lead"]
    season = lead["season"]
    lines = [f"{night_line(lead['night'])} ({lead['name']} model)",
             "",
             f"Season: {record_text(season)}, {units_text(season['units'])}. Every pick and every loss, "
             "locked before tip.",
             "",
             "Tonight's card drops this afternoon. Tail or fade? 👇",
             "",
             "Paper bets · 21+ · not betting advice"]
    return "\n".join(lines)


def reply(digest: str | None) -> str:
    """The first reply: where to check the record. Links in a reply keep the main post's reach."""
    lines = ["How to check us: every pick is written to a hash-chained log before tip, and the "
             f"log's fingerprint is published daily at {VERIFY_URL}"]
    if digest:
        lines.append(f"Today's fingerprint: {digest[:16]}")
    return "\n".join(lines)


# ---- the card ---------------------------------------------------------------------------------

CARD = Path(__file__).with_name("daily_post_card.html")


def tone(units: float) -> str:
    return "good" if units > 0 else "bad" if units < 0 else "flat"


def model_rows(f: dict) -> str:
    rows = []
    for m in f["models"]:
        night, season = m["night"], m["season"]
        beat = "–" if season["beat_close"] is None else f"{season['beat_close']:.0f}%"
        played = night["wins"] + night["losses"]
        rows.append(
            f'<tr class="{"lead" if m is f["lead"] else ""}"><td class="name">{html.escape(m["name"])}</td>'
            f'<td>{record_text(night) if played else "–"}</td>'
            f'<td class="{tone(night["units"]) if played else "flat"}">{units_text(night["units"]) if played else "–"}</td>'
            f'<td>{record_text(season)}</td><td class="{tone(season["units"])}">{units_text(season["units"])}</td>'
            f'<td>{beat}</td></tr>')
    return "\n".join(rows)


def trial_chips(slips: list[dict]) -> str:
    chips = []
    for s in slips:
        mark = "hit" if s["won"] else "missed"
        chips.append(f'<div class="chip {"good" if s["won"] else "bad"}"><b>{html.escape(s["name"])}</b>'
                     f' · {s["legs"]} legs · {american(s["payout"])} · {mark} ({s["hit"]}/{s["legs"]})</div>')
    return "".join(chips)


def card_html(f: dict, digest: str | None, slips: list[dict], logo_svg: str) -> str:
    lead = f["lead"]
    played = lead["night"]["wins"] + lead["night"]["losses"]
    return Template(CARD.read_text(encoding="utf-8")).substitute(
        logo=logo_svg, date=short_date(f["day"], weekday=True), lead_name=html.escape(lead["name"]),
        lead_record=record_text(lead["night"]) if played else "No picks",
        lead_units=units_text(lead["night"]["units"]), lead_tone=tone(lead["night"]["units"]),
        lead_count=played, season_record=record_text(lead["season"]),
        season_units=units_text(lead["season"]["units"]), season_tone=tone(lead["season"]["units"]),
        first_day=short_date(f["first_day"]), days=f["days"], rows=model_rows(f),
        trials=trial_chips(slips), digest=(digest or "")[:16], verify=VERIFY_URL, handle=HANDLE)


def find_edge() -> Path | None:
    found = shutil.which("msedge")
    return Path(found) if found else next((p for p in EDGE_PATHS if p.exists()), None)


def render(page: str, png: Path, browser: Path | None = None, run=subprocess.run,
           size: tuple[int, int] = (WIDTH, HEIGHT)) -> Path:
    """Save the page as a 2x PNG with headless Edge. Raises when no PNG comes out."""
    browser = browser or find_edge()
    if browser is None:
        raise FileNotFoundError("Microsoft Edge was not found, so the card cannot be drawn")
    png.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        source = Path(scratch) / "card.html"
        source.write_text(page, encoding="utf-8")
        run([str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=2", f"--window-size={size[0]},{size[1]}",
             f"--user-data-dir={Path(scratch) / 'profile'}", f"--screenshot={png}",
             source.as_uri()], check=False, capture_output=True, timeout=RENDER_TIMEOUT_SECONDS)
    if not png.exists():
        raise RuntimeError("Edge did not write the card")
    return png


PREVIEW = Path(__file__).with_name("daily_post_preview.html")
PREVIEW_SIZE = (600, 620)


def _linked(text: str) -> str:
    return html.escape(text).replace(VERIFY_URL, f'<a>{VERIFY_URL}</a>')


def preview_html(text: str, png: bytes, avatar_svg: str, reply_text: str | None = None,
                 time: str = "9:05 AM") -> str:
    """The post as it would read in an X feed: avatar, handle, caption, the card, and the reply."""
    reply_html = "" if not reply_text else (
        f'<article class="post reply"><div class="avatar">{avatar_svg}</div><div class="body">'
        f'<div class="who"><b>Ball Knowledge</b> <span>{HANDLE} · {time}</span></div>'
        f'<div class="text">{_linked(reply_text)}</div></div></article>')
    return Template(PREVIEW.read_text(encoding="utf-8")).substitute(
        avatar=avatar_svg, handle=HANDLE, text=_linked(text), reply=reply_html, time=time,
        image="data:image/png;base64," + base64.b64encode(png).decode())


def preview(stem: str, out: Path = POSTS, render_fn=None) -> Path:
    """Draw <stem>-preview.png from the saved card (<stem>.png), caption (<stem>.txt) and, when
    there is one, the reply (<stem>-reply.txt)."""
    reply_path = out / f"{stem}-reply.txt"
    page = preview_html((out / f"{stem}.txt").read_text(encoding="utf-8"), (out / f"{stem}.png").read_bytes(),
                        (ROOT / "assets" / "logo-mark.svg").read_text(encoding="utf-8"),
                        reply_path.read_text(encoding="utf-8") if reply_path.exists() else None,
                        "4:35 PM" if stem.endswith("-tonight") else "9:05 AM")
    size = (PREVIEW_SIZE[0], PREVIEW_SIZE[1] + (40 if reply_path.exists() else 0))
    return (render_fn or (lambda p, png: render(p, png, size=size)))(page, out / f"{stem}-preview.png")


def run(today: dt.date | None = None, day: str | None = None, out: Path = POSTS, render_fn=render) -> str:
    """Write <day>.png, <day>.txt and <day>-reply.txt for the last graded night. Returns one
    line for the log."""
    f = facts(nba_paper.load_ledger(), day)
    if f is None:
        return "Daily post: no graded picks for that day, so nothing to post."
    digest = fingerprint()
    out.mkdir(parents=True, exist_ok=True)
    png_path = out / f"{f['day']}.png"
    (out / f"{f['day']}.txt").write_text(caption(f), encoding="utf-8")
    (out / f"{f['day']}-reply.txt").write_text(reply(digest), encoding="utf-8")
    page = card_html(f, digest, trial_slips(f["day"]), LOGO.read_text(encoding="utf-8"))
    render_fn(page, png_path)
    return f"Daily post ready: {png_path.relative_to(ROOT) if png_path.is_relative_to(ROOT) else png_path}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", help="the game day to post (default: the last graded one)")
    parser.add_argument("--preview", action="store_true",
                        help="also draw <day>-preview.png: the post as it would read in an X feed")
    args = parser.parse_args()
    line = run(day=args.day)
    print(line)
    if args.preview and line.startswith("Daily post ready"):
        print(f"Preview: {preview(Path(line.split(': ', 1)[1]).stem)}")


if __name__ == "__main__":
    main()
