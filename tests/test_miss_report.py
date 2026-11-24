import pandas as pd
import pytest

from edgefinder.tracking import miss_report


def _row(n, *, side="under", result="loss", odds=-110, line=20.5, mean=18.5, actual=23.0,
         version="ewma-v1", stat="points", book="fanduel", status="settled"):
    return {"event_id": f"e{n}", "player": f"P{n}", "model_version": version, "stat": stat,
            "book": book, "status": status, "pick_side": side, "pick_odds": odds,
            "result": result if side else None,
            "pnl_units": (0.91 if result == "win" else -1.0) if side else None,
            "line": line, "model_mean": mean, "actual": actual}


def test_picks_are_split_by_side_with_how_far_off_the_projection_was():
    ledger = pd.DataFrame([_row(1, side="over", result="win", mean=22.0, actual=24.0),
                           _row(2, side="under", actual=23.0), _row(3, side="under", actual=21.0)])
    sides = miss_report.side_split(ledger, "ewma-v1")
    assert sides["over"] == {"n": 1, "win_pct": 100.0, "units": 0.91, "miss": 2.0}
    assert sides["under"] == {"n": 2, "win_pct": 0.0, "units": -2.0, "miss": 3.5}


def test_picks_are_split_by_price():
    ledger = pd.DataFrame([_row(1, odds=-150), _row(2, odds=-110), _row(3, odds=-100, result="win"),
                           _row(4, odds=130, result="win")])
    prices = miss_report.price_split(ledger, "ewma-v1")
    assert [(label, facts["n"]) for label, facts in prices.items()] == [
        ("-130 or shorter", 1), ("-129 to -101", 1), ("even or plus money", 2)]
    assert prices["even or plus money"]["win_pct"] == 100.0


def test_the_share_of_disagreement_that_came_true_uses_every_settled_line():
    rows = []
    for n in range(miss_report.MIN_LINES):
        gap = (n % 5) - 2 or 1                       # model sits 1-2 points off the line
        # actual lands exactly half way between the line and the projection
        rows.append(_row(n, side=None, mean=20.5 + gap, actual=20.5 + gap / 2))
    share = miss_report.disagreement_share(pd.DataFrame(rows), "ewma-v1")
    assert share["n"] == miss_report.MIN_LINES
    assert share["share"] == pytest.approx(0.5)
    assert share["plus_minus"] == pytest.approx(0.0, abs=1e-9)


def test_too_few_lines_give_no_share():
    assert miss_report.disagreement_share(pd.DataFrame([_row(1)]), "ewma-v1") is None


def test_only_settled_fanduel_points_rows_count():
    ledger = pd.DataFrame([_row(1), _row(2, stat="rebounds"), _row(3, book="kalshi"),
                           _row(4, status="pending"), _row(5, version="minutes-v1")])
    assert miss_report.side_split(ledger, "ewma-v1")["under"]["n"] == 1


def test_the_report_names_each_model_and_says_what_the_misses_mean():
    rows = [_row(n, side="under" if n % 2 else None, mean=19.0, actual=21.0 + n % 3)
            for n in range(miss_report.MIN_LINES)]
    text = "\n".join(miss_report.report_lines(pd.DataFrame(rows)))
    assert "What the misses say" in text and "[ewma-v1]" in text
    assert "under" in text and "scored +" in text
    assert "of its disagreement with the line came true" in text


def test_an_empty_ledger_reports_nothing():
    assert miss_report.report_lines(pd.DataFrame(columns=list(_row(0)))) == []
