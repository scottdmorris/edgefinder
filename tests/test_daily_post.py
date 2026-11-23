"""The morning X post: honest numbers (a fixed lead model, losses shown), a caption that fits,
and a card drawn by headless Edge. Nothing here posts anything."""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from edgefinder.tracking import nba_paper, suggested_record

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "daily_post.py"
spec = importlib.util.spec_from_file_location("daily_post_under_test", SCRIPT)
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)


def pick(day: str, model: str, result: str, pnl: float, clv: float | None = 1.0, **extra) -> dict:
    return {column: None for column in nba_paper.COLUMNS} | {
        "game_date": day, "model_version": model, "book": "fanduel", "stat": "points",
        "status": "settled", "pick_side": "over", "result": result, "pnl_units": pnl,
        "clv_pct": clv} | extra


def ledger() -> pd.DataFrame:
    rows = [pick("2026-11-15", "context-v2", "win", .9), pick("2026-11-15", "context-v2", "loss", -1),
            pick("2026-11-16", "context-v2", "loss", -1, clv=-2.0),
            pick("2026-11-16", "ewma-v1", "win", .9), pick("2026-11-16", "ewma-v1", "win", .9),
            pick("2026-11-16", "context-v2", "win", 5.0, book="kalshi"),           # not FanDuel
            pick("2026-11-16", "context-v2", "win", 1.0, stat="rebounds"),       # not points
            pick("2026-11-17", "context-v2", None, None, status="pending")]       # not graded
    return pd.DataFrame(rows, columns=nba_paper.COLUMNS)


def test_leads_with_the_fixed_model_even_on_a_night_another_did_better():
    f = post.facts(ledger())
    assert f["day"] == "2026-11-16" and f["first_day"] == "2026-11-15" and f["days"] == 2
    assert f["lead"]["id"] == "context-v2"
    assert f["lead"]["night"] == {"wins": 0, "losses": 1, "units": -1.0, "beat_close": 0.0}
    assert f["lead"]["season"]["wins"] == 1 and f["lead"]["season"]["losses"] == 2
    assert [m["name"] for m in f["models"]] == ["Sharpest", "Simple"]


def test_a_chosen_day_counts_the_season_only_up_to_it_and_an_ungraded_day_has_no_post():
    f = post.facts(ledger(), "2026-11-15")
    assert f["lead"]["season"]["wins"] == 1 and f["days"] == 1
    assert post.facts(ledger(), "2026-11-17") is None
    assert post.facts(pd.DataFrame(columns=nba_paper.COLUMNS)) is None


def test_the_caption_fits_x_shows_losses_and_carries_the_disclaimer():
    f = post.facts(ledger())
    text = post.caption(f)
    assert len(text) <= post.MAX_CAPTION
    assert text.startswith("0-1 last night, −1.00u 📉 (Sharpest model)")
    assert "Season: 1-2, −1.10u" in text and "Tonight's card" in text
    assert "21+" in text and "not betting advice" in text and post.VERIFY_URL not in text
    f["lead"]["night"] = {"wins": 2, "losses": 0, "units": 1.8, "beat_close": None}
    assert post.caption(f).startswith("2-0 last night, +1.80u 📈")
    f["lead"]["night"] = {"wins": 0, "losses": 0, "units": 0.0, "beat_close": None}
    assert post.caption(f).startswith("No graded picks last night")


def test_the_reply_carries_the_link_and_the_fingerprint():
    assert post.VERIFY_URL in post.reply("b" * 64) and "bbbbbbbbbbbbbbbb" in post.reply("b" * 64)
    assert "fingerprint:" not in post.reply(None)


def test_reads_the_newest_published_fingerprint(tmp_path):
    digests = tmp_path / "DIGESTS.md"
    digests.write_text("| Date | Entries | Fingerprint |\n|---|---|---|\n"
                       "| 2026-11-15 | 10 | `old` |\n| 2026-11-16 | 12 | `new` |\n", encoding="utf-8")
    assert post.fingerprint(digests) == "new"
    assert post.fingerprint(tmp_path / "missing.md") is None


def test_trial_results_for_the_day_skip_ungraded_and_void_slips():
    slip = {"legs": [{"player_id": i} for i in range(10)], "payout": 13.25, "day": "2026-11-16"}
    with suggested_record.connect() as db:
        for offer, trial, result in [("a", "long-shot-v1", {"status": "loss", "legs": ["win"] * 8 + ["loss"] * 2}),
                                     ("b", "higher-hit-v1", {"status": "void", "legs": ["void"] * 10}),
                                     ("c", "other-day", None)]:
            db.execute("INSERT INTO offers VALUES (?, ?, ?)",
                       (offer, json.dumps(slip), json.dumps(result) if result else None))
            db.execute("INSERT INTO experiment VALUES (?, ?, ?)", (trial, "2026-11-16", offer))
    assert post.trial_slips("2026-11-16") == [
        {"name": "Long shot", "legs": 10, "hit": 8, "payout": 13.25, "won": False}]
    assert post.trial_slips("2026-11-20") == []


def test_the_card_fills_every_slot_and_escapes_names():
    f = post.facts(ledger())
    f["models"][1]["name"] = "<Simple>"
    page = post.card_html(f, "f" * 64, [{"name": "Long shot", "legs": 10, "hit": 8, "payout": 13.25,
                                          "won": False}], "<svg></svg>")
    assert "$" not in page and "&lt;Simple&gt;" in page
    assert "missed (8/10)" in page and "+1,225" in page and post.HANDLE in page
    assert 'class="lead"' in page and "−1.00u" in page


def test_rendering_asks_edge_for_a_2x_screenshot_and_fails_loudly_without_one(tmp_path, monkeypatch):
    seen = []

    def fake_edge(args, **kwargs):
        seen.append(args)
        Path(args[[a.startswith("--screenshot=") for a in args].index(True)].split("=", 1)[1]).write_bytes(b"png")
    png = post.render("<html></html>", tmp_path / "out" / "card.png", Path("edge.exe"), run=fake_edge)
    assert png.read_bytes() == b"png"
    assert "--force-device-scale-factor=2" in seen[0] and f"--window-size={post.WIDTH},{post.HEIGHT}" in seen[0]
    with pytest.raises(RuntimeError):
        post.render("<html></html>", tmp_path / "none.png", Path("edge.exe"), run=lambda *a, **k: None)
    stale = tmp_path / "stale.png"                   # an earlier card must not pass for a new one
    stale.write_bytes(b"old")
    with pytest.raises(RuntimeError):
        post.render("<html></html>", stale, Path("edge.exe"), run=lambda *a, **k: None)
    assert stale.read_bytes() == b"old"
    monkeypatch.setattr(post, "find_edge", lambda: None)
    with pytest.raises(FileNotFoundError, match="Edge"):
        post.render("x", tmp_path / "n.png", run=lambda *a, **k: None)


def test_run_writes_the_caption_and_the_card(monkeypatch, tmp_path):
    monkeypatch.setattr(post.nba_paper, "load_ledger", ledger)
    monkeypatch.setattr(post, "DIGESTS", tmp_path / "none.md")
    drawn = []
    line = post.run(out=tmp_path, render_fn=lambda page, png: drawn.append(png) or png)
    assert drawn == [tmp_path / "2026-11-16.png"] and "Daily post ready" in line
    assert "0-1" in (tmp_path / "2026-11-16.txt").read_text(encoding="utf-8")
    assert post.VERIFY_URL in (tmp_path / "2026-11-16-reply.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(post.nba_paper, "load_ledger", lambda: pd.DataFrame(columns=nba_paper.COLUMNS))
    assert "nothing to post" in post.run(out=tmp_path, render_fn=lambda *a: None)


def test_an_unpublished_record_holds_the_reply_and_keeps_the_fingerprint_off_the_card(monkeypatch, tmp_path):
    monkeypatch.setattr(post.nba_paper, "load_ledger", ledger)
    monkeypatch.setattr(post, "fingerprint", lambda: "abcdef0123456789ffff")
    pages = []
    post.run(out=tmp_path, render_fn=lambda page, png: pages.append(page))
    assert (tmp_path / "2026-11-16-reply.txt").exists() and "abcdef0123456789" in pages[0]
    line = post.run(out=tmp_path, render_fn=lambda page, png: pages.append(page), published=False)
    assert "reply held" in line and not (tmp_path / "2026-11-16-reply.txt").exists()
    assert "fingerprint" not in pages[1] and "$" not in pages[1]


def test_the_feed_preview_shows_the_caption_link_and_card(tmp_path):
    (tmp_path / "2026-11-16.txt").write_text(f"Daily record <b>\n{post.VERIFY_URL}", encoding="utf-8")
    (tmp_path / "2026-11-16.png").write_bytes(b"png")
    pages = []
    target = post.preview("2026-11-16", out=tmp_path, render_fn=lambda page, png: pages.append(page) or png)
    assert target == tmp_path / "2026-11-16-preview.png"
    page = pages[0]
    assert "$" not in page and "&lt;b&gt;" in page and f"<a>{post.VERIFY_URL}</a>" in page
    assert "data:image/png;base64,cG5n" in page and post.HANDLE in page
    assert 'class="post reply"' not in page and "9:05 AM" in page


def test_the_preview_shows_the_reply_and_an_afternoon_time_for_tonights_card(tmp_path):
    for stem in ("2026-11-16", "2026-11-17-tonight"):
        (tmp_path / f"{stem}.txt").write_text("text", encoding="utf-8")
        (tmp_path / f"{stem}.png").write_bytes(b"png")
    (tmp_path / "2026-11-16-reply.txt").write_text(f"check {post.VERIFY_URL}", encoding="utf-8")
    pages = []
    post.preview("2026-11-16", out=tmp_path, render_fn=lambda page, png: pages.append(page))
    post.preview("2026-11-17-tonight", out=tmp_path, render_fn=lambda page, png: pages.append(page))
    assert 'class="post reply"' in pages[0] and f"check <a>{post.VERIFY_URL}</a>" in pages[0]
    assert "4:35 PM" in pages[1] and 'class="post reply"' not in pages[1]
