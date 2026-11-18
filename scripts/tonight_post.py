"""Make the afternoon X post: tonight's card. The Sharpest model's picks for today, as already
locked in the hash-chained log, and the Long shot trial's slip when one is recorded.

The snapshot job refreshes it each run, since picks for later games are locked closer to their
tip, so the newest file is the one to post. The morning post grades the same picks. Files land
in data/posts/ as <day>-tonight.png and .txt. Nothing is posted: you post them.

Usage:  python scripts/tonight_post.py [--day YYYY-MM-DD] [--preview]
"""

import argparse
import datetime as dt
import html
import json
import sqlite3
import sys
from pathlib import Path
from string import Template

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily_post as dp  # noqa: E402  (same folder; it puts src on the path)

from edgefinder.data import nba_players  # noqa: E402
from edgefinder.data.nba_snapshot_plan import EASTERN  # noqa: E402
from edgefinder.tracking import nba_paper, suggested_record  # noqa: E402

CARD = Path(__file__).with_name("tonight_post_card.html")
MAX_ROWS = 6                  # what fits the card at a size a phone can read
STAT_WORDS = {"points": "pts", "rebounds": "reb", "assists": "ast", "threes": "3PM"}


def _abbr(team: str) -> str:
    return nba_players.team_abbreviation(team) or team.split()[-1][:3].upper()


def _tip(commence: str) -> str:
    return pd.Timestamp(commence).tz_convert(EASTERN).strftime("%I:%M %p").lstrip("0")


def _picks_word(n: int) -> str:
    return f"{n} pick" if n == 1 else f"{n} picks"


def _american(odds: float) -> str:
    return f"+{odds:.0f}" if odds > 0 else f"−{abs(odds):.0f}"


def picks(ledger: pd.DataFrame, day: str) -> list[dict]:
    """The lead model's locked FanDuel points picks for `day`, one per player (the newest), by
    tip time and then by edge."""
    rows = ledger[(ledger["game_date"].astype(str) == day) & (ledger["model_version"] == dp.LEAD_MODEL)
                  & (ledger["book"] == "fanduel") & (ledger["stat"] == "points")
                  & ledger["pick_side"].notna()]
    if rows.empty:
        return []
    rows = rows.sort_values("recorded_at").drop_duplicates(["event_id", "player"], keep="last")
    out = []
    for r in rows.itertuples():
        over = r.pick_side == "over"
        blend = nba_paper.MODEL_WEIGHT * float(r.model_p_over) + (1 - nba_paper.MODEL_WEIGHT) * float(r.fair_p_over)
        out.append({"player": r.player, "game": f"{_abbr(r.away)} @ {_abbr(r.home)}",
                    "tip": _tip(r.commence_time), "commence": str(r.commence_time),
                    "bet": f"{'Over' if over else 'Under'} {float(r.line):g} pts",
                    "odds": _american(float(r.pick_odds)),
                    "chance": round(100 * (blend if over else 1 - blend)),
                    "edge": round(100 * float(r.pick_ev), 1), "locked": str(r.recorded_at)})
    return sorted(out, key=lambda p: (p["commence"], -p["edge"]))


def long_shot(day: str, path: Path | None = None) -> dict | None:
    """The Long shot trial's slip for `day`, if one was recorded."""
    db_path = path or suggested_record.DB_PATH
    if not db_path.exists():
        return None
    try:
        with suggested_record.connect(db_path) as db:
            found = db.execute("SELECT o.payload FROM experiment e JOIN offers o ON o.id = e.offer "
                               "WHERE e.trial = ? AND e.day = ?",
                               (suggested_record.LONG_SHOT_EXPERIMENT["id"], day)).fetchone()
    except sqlite3.Error:
        return None
    if not found:
        return None
    slip = json.loads(found[0])
    legs = [{"player": leg.get("player", "?"),
             "bet": f"{leg['side']} {leg['line']:g} {STAT_WORDS.get(leg['stat'], leg['stat'])}"}
            for leg in slip["legs"]]
    return {"legs": legs, "payout": float(slip["payout"]), "chance": 100 * float(slip["probability"])}


def caption(day: str, plays: list[dict], slip: dict | None) -> str:
    """Under 280 characters: what is on the card, the best edge, and when it gets graded."""
    top = max(plays, key=lambda p: p["edge"])
    lines = [f"Tonight's card 🏀 {_picks_word(len(plays))} from the Sharpest model, locked before tip."]
    if slip:
        lines.append(f"Plus a {len(slip['legs'])}-leg Long shot at {dp.american(slip['payout'])}.")
    lines += ["", f"Biggest edge: {top['player']} {top['bet']} ({top['odds']})",
              "", "Tail or fade? Graded tomorrow morning, wins and losses.",
              "", "Paper bets · 21+ · not betting advice"]
    return "\n".join(lines)


def card_html(day: str, plays: list[dict], slip: dict | None, logo_svg: str, as_of: str) -> str:
    shown = plays[:MAX_ROWS]
    rows = "\n".join(
        f'<tr><td class="who"><b>{html.escape(p["player"])}</b><span>{p["game"]} · {p["tip"]}</span></td>'
        f'<td class="bet">{html.escape(p["bet"])}</td><td>{p["odds"]}</td><td>{p["chance"]}%</td>'
        f'<td class="edge">+{p["edge"]:.1f}%</td></tr>' for p in shown)
    more = (f'<p class="more">+{len(plays) - MAX_ROWS} more picks in the app</p>'
            if len(plays) > MAX_ROWS else "")
    if slip:
        legs = "".join(f'<li><b>{html.escape(leg["player"])}</b> {html.escape(leg["bet"])}</li>'
                       for leg in slip["legs"])
        side = (f'<aside class="longshot"><div class="label">Long shot · {len(slip["legs"])} legs · Kalshi</div>'
                f'<div class="pays num">{dp.american(slip["payout"])}</div>'
                f'<div class="sub">about {slip["chance"]:.1f}% to hit, by our estimate</div>'
                f'<ol>{legs}</ol></aside>')
    else:
        side = ""
    return Template(CARD.read_text(encoding="utf-8")).substitute(
        logo=logo_svg, date=dp.short_date(day, weekday=True), count=_picks_word(len(plays)), rows=rows, more=more,
        longshot=side, layout="with-side" if slip else "solo", as_of=as_of, handle=dp.HANDLE)


def run(day: str | None = None, out: Path = dp.POSTS, render_fn=dp.render, now: dt.datetime | None = None) -> str:
    """Write <day>-tonight.png and .txt. Redraws only when the picks or the slip changed.
    Returns one line for the log."""
    now = now or dt.datetime.now(EASTERN)
    day = day or now.date().isoformat()
    plays = picks(nba_paper.load_ledger(), day)
    if not plays:
        return f"Tonight's card: no Sharpest picks locked for {day} yet."
    slip = long_shot(day)
    text = caption(day, plays, slip)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"{day}-tonight"
    key = json.dumps({"plays": plays, "slip": slip}, sort_keys=True)
    key_path = stem.with_suffix(".key")
    if key_path.exists() and key_path.read_text(encoding="utf-8") == key and stem.with_suffix(".png").exists():
        return f"Tonight's card unchanged: {_picks_word(len(plays))}."
    latest = max(pd.Timestamp(p["locked"]) for p in plays).tz_convert(EASTERN)
    page = card_html(day, plays, slip, dp.LOGO.read_text(encoding="utf-8"),
                     latest.strftime("%I:%M %p").lstrip("0"))
    stem.with_suffix(".txt").write_text(text, encoding="utf-8")
    render_fn(page, stem.with_suffix(".png"))
    key_path.write_text(key, encoding="utf-8")
    return f"Tonight's card ready: {_picks_word(len(plays))}{' and a Long shot' if slip else ''}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", help="the game day (default: today, Eastern time)")
    parser.add_argument("--preview", action="store_true",
                        help="also draw <day>-tonight-preview.png: the post as it would read in an X feed")
    args = parser.parse_args()
    line = run(args.day)
    print(line)
    if args.preview and "no Sharpest picks" not in line:
        day = args.day or dt.datetime.now(EASTERN).date().isoformat()
        print(f"Preview: {dp.preview(f'{day}-tonight')}")


if __name__ == "__main__":
    main()
