"""The paper trial of FanDuel's X+ lines for rebounds, assists and threes."""

import datetime as dt

import pandas as pd
import pytest

from edgefinder.tracking import nba_alt, nba_alt_stats

EVENT = {"event_id": "e1", "commence_time": "2099-11-24T00:00:00Z",
         "home": "Charlotte Hornets", "away": "Memphis Grizzlies"}
WHEN, DAY = "2099-11-23T17:00:00+00:00", "2099-11-23"


def _rows(stat="rebounds", threshold_line=5.5, odds=110, mean=6.4, version="ewma-v1"):
    return nba_alt_stats.build_rows(
        EVENT, [{"player": "Miller", "line": threshold_line, "over_odds": odds}],
        {"Miller": {"player_id": 7, "mean": mean}}, WHEN, DAY, model_version=version, stat=stat)


def test_a_rebounds_rung_is_priced_with_the_stats_own_spread_and_can_be_a_pick():
    (row,) = _rows()
    assert (row["stat"], row["threshold"], row["over_odds"]) == ("rebounds", 6, 110)
    assert row["model_p"] == pytest.approx(
        nba_alt.p_at_least(6, 6.4, nba_alt_stats.dispersion("rebounds")))
    # the Simple model makes no points X+ picks; on the other stats it is the trial's model
    assert row["is_pick"] is True and row["pick_ev"] > 0
    assert set(row) == set(nba_alt_stats.COLUMNS)


def test_a_tipped_game_or_an_unknown_stat_prices_nothing():
    assert nba_alt_stats.build_rows(EVENT | {"commence_time": "2000-01-01T00:00:00Z"},
                                    [{"player": "Miller", "line": 5.5, "over_odds": 110}],
                                    {"Miller": {"player_id": 7, "mean": 6.4}}, WHEN, DAY,
                                    model_version="ewma-v1", stat="rebounds") == []
    assert _rows(stat="blocks") == []


def test_rows_are_kept_once_per_game_player_stat_rung_and_model(tmp_path):
    path = tmp_path / "alt_stats.csv"
    assert nba_alt_stats.append_rows(_rows(), path) == 1
    assert nba_alt_stats.append_rows(_rows(), path) == 0
    assert nba_alt_stats.append_rows(_rows(stat="assists"), path) == 1
    assert nba_alt_stats.append_rows(_rows(threshold_line=7.5), path) == 1
    assert list(nba_alt_stats.load_ledger(path).columns) == nba_alt_stats.COLUMNS


def _games(reb=7, ast=2):
    return pd.DataFrame([{"player_id": 7, "game_date": pd.Timestamp(DAY), "pts": 20, "reb": reb,
                          "ast": ast, "fg3m": 1, "minutes": 33.0, "game_id": "g1", "wl": "W"}])


def test_settling_grades_each_rung_on_its_own_stat(tmp_path):
    ledger = pd.DataFrame(_rows() + _rows(stat="assists", threshold_line=3.5, odds=150, mean=4.0))
    settled = nba_alt_stats.settle(ledger, _games(reb=7, ast=2), dt.date(2099, 11, 24))
    by_stat = settled.set_index("stat")
    assert by_stat.loc["rebounds", "actual"] == 7 and by_stat.loc["rebounds", "result"] == "win"
    assert by_stat.loc["rebounds", "pnl_units"] == pytest.approx(1.10)
    assert by_stat.loc["assists", "actual"] == 2 and by_stat.loc["assists", "result"] == "loss"


def test_the_summary_is_split_by_stat():
    assists = _rows(stat="assists", threshold_line=3.5, odds=150, mean=4.0)
    ledger = nba_alt_stats.settle(pd.DataFrame(_rows() + assists),
                                  _games(reb=7, ast=2), dt.date(2099, 11, 24))
    lines = nba_alt_stats.report_lines(ledger)
    assert lines[1].startswith("X+ trial, other stats")
    assert any(line.strip().startswith("rebounds") and "1-0" in line for line in lines)
    assert any(line.strip().startswith("assists") and "0-1" in line for line in lines)
    assert nba_alt_stats.report_lines(pd.DataFrame(columns=nba_alt_stats.COLUMNS)) == []
