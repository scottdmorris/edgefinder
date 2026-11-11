import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "nba_kalshi_backtest.py"
    spec = importlib.util.spec_from_file_location("nba_kalshi_backtest_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def game_log(points):
    return pd.DataFrame({"player_id": 7, "game_id": range(len(points)),
                         "game_date": pd.date_range("2025-10-01", periods=len(points)).astype(str),
                         "pts": points})


def test_recent_rate_counts_only_games_before_the_one_priced(script):
    # 20 games under 20 points, then a 40-point game: that game's own score must not count
    games = game_log([10] * script.RECENT_GAMES + [40, 10])
    markets = pd.DataFrame({"player_id": 7, "game_id": [script.RECENT_GAMES, script.RECENT_GAMES + 1],
                            "threshold": 20})

    rates = script.recent_rates(markets, games)

    assert rates.iloc[0] == 0.0
    assert rates.iloc[1] == pytest.approx(1 / script.RECENT_GAMES)


def test_recent_rate_is_missing_without_enough_games(script):
    games = game_log([25] * script.RECENT_GAMES)
    markets = pd.DataFrame({"player_id": [7], "game_id": [script.RECENT_GAMES - 1], "threshold": [20]})

    assert np.isnan(script.recent_rates(markets, games).iloc[0])


def test_buying_yes_pays_the_fee_win_or_lose(script):
    markets = pd.DataFrame({"yes_ask": [0.5, 0.5], "hit": [1, 0]})

    won, lost = script.yes_units(markets)

    fee = 0.07 * 0.5 * 0.5 / 0.5
    assert won == pytest.approx(1.0 - fee)
    assert lost == pytest.approx(-1.0 - fee)


def test_lock_slip_needs_every_leg_and_one_leg_a_player(script):
    def night(date, hits):
        return pd.DataFrame({"game_date": date, "player_id": [1, 1, 2, 3], "recent_rate": 0.95,
                             "mid": 0.85, "yes_ask": 0.9, "hit": hits})
    # night one: all three players hit; night two: one misses
    frame = pd.concat([night("2026-01-01", [1, 1, 1, 1]), night("2026-01-02", [1, 1, 1, 0])],
                      ignore_index=True)

    slips = script.lock_slips(frame, np.random.default_rng(0))

    assert slips["nights"] == 2
    assert slips["cost"] == pytest.approx(0.9 ** 3)
    assert slips["won"] == 0.5


def test_split_night_is_the_middle_game_night(script):
    frame = pd.DataFrame({"game_date": ["2026-01-03", "2026-01-01", "2026-01-02", "2026-01-04"]})

    assert script.split_night(frame) == "2026-01-03"
