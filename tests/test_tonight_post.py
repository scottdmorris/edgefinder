"""Tonight's card: the lead model's locked picks for the day and the Long shot slip, drawn once
per change, with a caption that fits X. Nothing here posts anything."""

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

from edgefinder.tracking import nba_paper, suggested_record

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("tonight_post_under_test", SCRIPTS / "tonight_post.py")
tonight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tonight)

DAY = "2026-11-18"


def row(player: str, side: str = "under", ev: float = .05, odds: float = -110, tip: str = "2026-11-19T00:10:00Z",
        recorded: str = "2026-11-18T20:00:00+00:00", **extra) -> dict:
    return {column: None for column in nba_paper.COLUMNS} | {
        "game_date": DAY, "event_id": tip, "commence_time": tip, "home": "San Antonio Spurs",
        "away": "Detroit Pistons", "player": player, "line": 20.5, "model_version": "context-v2",
        "model_p_over": .4, "fair_p_over": .5, "pick_side": side, "pick_odds": odds, "pick_ev": ev,
        "status": "pending", "stat": "points", "book": "fanduel", "recorded_at": recorded} | extra


def ledger(rows: list[dict] | None = None) -> pd.DataFrame:
    rows = rows if rows is not None else [
        row("Early Big Edge", ev=.08), row("Early Small Edge", ev=.02),
        row("Late Game", ev=.10, tip="2026-11-19T03:10:00Z"),
        row("Moved Line", ev=.03, recorded="2026-11-18T19:00:00+00:00"),
        row("Moved Line", ev=.04, odds=105, side="over", recorded="2026-11-18T21:00:00+00:00"),
        row("Other Model", model_version="ewma-v1"), row("Kalshi Row", book="kalshi"),
        row("No Pick", pick_side=None), row("Other Day", game_date="2026-11-17")]
    return pd.DataFrame(rows, columns=nba_paper.COLUMNS)


def test_lists_the_lead_models_picks_by_tip_then_edge_keeping_the_newest_line():
    plays = tonight.picks(ledger(), DAY)
    assert [p["player"] for p in plays] == ["Early Big Edge", "Moved Line", "Early Small Edge", "Late Game"]
    moved = plays[1]
    assert moved["bet"] == "Over 20.5 pts" and moved["odds"] == "+105" and moved["edge"] == 4.0
    first = plays[0]
    assert first["game"] == "DET @ SAS" and first["tip"] == "7:10 PM" and first["odds"] == "−110"
    assert first["chance"] == round(100 * (1 - (.3 * .4 + .7 * .5)))     # the under's blended chance
    assert tonight.picks(ledger(), "2026-11-20") == []


def test_reads_the_long_shot_slip_recorded_for_the_day():
    legs = [{"player": f"P{i}", "side": "Over", "line": 9.5, "stat": "points"} for i in range(10)]
    with suggested_record.connect() as db:
        db.execute("INSERT INTO offers VALUES (?, ?, NULL)",
                   ("x", json.dumps({"legs": legs, "payout": 13.25, "probability": .075})))
        db.execute("INSERT INTO experiment VALUES (?, ?, ?)", ("long-shot-v1", DAY, "x"))
        db.execute("INSERT INTO experiment VALUES (?, ?, ?)", ("higher-hit-v1", "2026-11-19", "x"))
    slip = tonight.long_shot(DAY)
    assert slip["payout"] == 13.25 and round(slip["chance"], 1) == 7.5
    assert slip["legs"][0] == {"player": "P0", "bet": "Over 9.5 pts"}
    assert tonight.long_shot("2026-11-19") is None


def test_the_caption_fits_names_the_biggest_edge_and_the_long_shot():
    plays = tonight.picks(ledger(), DAY)
    slip = {"legs": [{}] * 10, "payout": 13.25, "chance": 7.5}
    text = tonight.caption(DAY, plays, slip)
    assert len(text) <= 280
    assert "4 picks from the Sharpest model" in text and "10-leg Long shot at +1,225" in text
    assert "Biggest edge: Late Game Under 20.5 pts (−110)" in text
    assert "21+" in text and "not betting advice" in text
    assert "Long shot" not in tonight.caption(DAY, plays, None)


def test_the_card_caps_its_rows_and_shows_the_long_shot_beside_them():
    many = tonight.picks(ledger([row(f"Player {i}", ev=.01 * i) for i in range(9)]), DAY)
    logo = "<svg></svg>"
    page = tonight.card_html(DAY, many, None, logo, "4:30 PM")
    assert page.count("<tr><td") == tonight.MAX_ROWS and "+3 more picks in the app" in page
    assert 'class="solo"' in page and "$" not in page
    slip = {"legs": [{"player": "<A>", "bet": "Over 9.5 pts"}], "payout": 13.25, "chance": 7.5}
    side = tonight.card_html(DAY, many[:2], slip, logo, "4:30 PM")
    assert 'class="with-side"' in side and "&lt;A&gt;" in side and "+1,225" in side and "more picks" not in side


def test_run_draws_once_per_change(monkeypatch, tmp_path):
    current = {"ledger": ledger()}
    monkeypatch.setattr(tonight.nba_paper, "load_ledger", lambda: current["ledger"])
    drawn = []

    def draw(page, png):
        drawn.append(png)
        png.write_bytes(b"png")
    now = dt.datetime(2026, 11, 18, 16, 30, tzinfo=tonight.EASTERN)
    assert tonight.run(out=tmp_path, render_fn=draw, now=now).startswith("Tonight's card ready: 4 picks")
    assert tonight.run(out=tmp_path, render_fn=draw, now=now).startswith("Tonight's card unchanged")
    current["ledger"] = ledger(ledger().to_dict("records")[:1])
    tonight.run(out=tmp_path, render_fn=draw, now=now)
    assert drawn == [tmp_path / f"{DAY}-tonight.png"] * 2
    assert "1 pick from" in (tmp_path / f"{DAY}-tonight.txt").read_text(encoding="utf-8")
    current["ledger"] = ledger([])
    assert "no Sharpest picks" in tonight.run(out=tmp_path, render_fn=draw, now=now)
