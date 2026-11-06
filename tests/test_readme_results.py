import importlib.util
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "readme_results.py"
    spec = importlib.util.spec_from_file_location("readme_results_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pick(version, result, units, clv, book="fanduel", stat="points", status="settled", side="over"):
    return {"model_version": version, "result": result, "pnl_units": units, "clv_pct": clv,
            "book": book, "stat": stat, "status": status, "pick_side": side}


def test_each_model_gets_its_own_row_with_record_units_and_how_often_it_beat_the_close(script):
    ledger = pd.DataFrame([
        pick("ewma-v1", "win", 0.9, 4.0), pick("ewma-v1", "loss", -1.0, -2.0),
        pick("ewma-v1", "win", 0.5, None),                        # no closing price: not counted
        pick("minutes-v1", "loss", -1.0, 1.0)])
    text = script.table(ledger)
    assert "| Simple (`ewma-v1`) | 3 | 2-1 | +0.40 | 50% of 2 |" in text
    assert "| Smarter (`minutes-v1`) | 1 | 0-1 | -1.00 | 100% of 1 |" in text


def test_only_graded_fanduel_points_picks_are_counted(script):
    ledger = pd.DataFrame([
        pick("ewma-v1", "win", 0.9, 1.0),
        pick("ewma-v1", "win", 0.9, 1.0, book="kalshi"),          # another source
        pick("ewma-v1", "win", 0.9, 1.0, stat="rebounds"),        # another stat
        pick("ewma-v1", None, None, None, status="pending"),      # not graded yet
        pick("ewma-v1", "win", 0.9, 1.0, side=None)])             # a line, not a pick
    assert "| Simple (`ewma-v1`) | 1 | 1-0 | +0.90 | 100% of 1 |" in script.table(ledger)


def test_nothing_graded_says_so_instead_of_an_empty_table(script):
    empty = pd.DataFrame(columns=["model_version", "result", "pnl_units", "clv_pct", "book",
                                  "stat", "status", "pick_side"])
    assert "none graded yet" in script.table(empty)
