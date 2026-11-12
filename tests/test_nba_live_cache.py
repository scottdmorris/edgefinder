"""Streamlit caches survive game records fetched during a module reload."""

import pickle
from dataclasses import asdict

import pytest

from edgefinder.data import nba_live
from edgefinder.ui import nba_live_tab as tab


def _stale(record):
    # An old class has the same import path but a different identity after reload.
    old_class = type(type(record).__name__, (type(record),),
                     {"__module__": nba_live.__name__})
    old = old_class(**asdict(record))
    with pytest.raises(pickle.PicklingError):
        pickle.dumps(old)
    return old


def test_live_caches_store_plain_values_and_restore_current_records(monkeypatch):
    game = nba_live.LiveGame("one", 2, "1st Qtr", 1, "10:00", "MIL", "BOS", 4, 6)
    player = nba_live.PlayerLine(7, "Example", "BOS", 6, 2, 1, 5.0, True, True)
    shot = nba_live.Shot("BOS", "Example", True, 10, 20, 1, 5, False, "Made shot")
    play = nba_live.Play(1, "Q1", "10:00", "BOS", "Made shot", "MIL 4 - BOS 6", 4, 6)
    detail = nba_live.GameDetail({7: _stale(player)}, {"BOS": {"foulsPersonal": 1.0}},
                                {"BOS": [6]}, [_stale(shot)], [_stale(play)])
    stale_detail = type("GameDetail", (nba_live.GameDetail,),
                        {"__module__": nba_live.__name__})(
                            detail.players, detail.team_stats, detail.period_scores,
                            detail.shots, detail.plays)
    with pytest.raises(pickle.PicklingError):
        pickle.dumps(stale_detail)
    calls = []

    def fetch(kind, result):
        def read(*args):
            calls.append(kind)
            return result
        return read

    monkeypatch.setattr(nba_live, "fetch_games", fetch("games", [_stale(game)]))
    monkeypatch.setattr(nba_live, "fetch_box", fetch("box", {7: _stale(player)}))
    monkeypatch.setattr(nba_live, "fetch_detail", fetch("detail", stale_detail))
    caches = (tab._game_rows, tab._box_rows, tab._detail_rows)
    for cache in caches:
        cache.clear()
    try:
        for _ in range(2):
            assert tab._games() == [game]
            assert tab._box("one") == {7: player}
            restored = tab._detail("one", "MIL", "BOS")
            assert restored.players == {7: player}
            assert restored.shots == [shot] and restored.plays == [play]
            assert restored.team_stats == detail.team_stats
            assert restored.period_scores == detail.period_scores
            restored.team_stats["BOS"]["foulsPersonal"] = 99
        assert calls == ["games", "box", "detail"]
    finally:
        for cache in caches:
            cache.clear()
