"""The Long shot style: one many-leg slip of the likeliest worthwhile legs, at most two players
a game, and its own frozen paper trial on Kalshi, kept apart from the higher-hit trial."""

import datetime as dt

import pandas as pd
import pytest

from edgefinder.api import suggestion_service as ss
from edgefinder.tracking import nba_parlay, suggested_record as sr

NOW = dt.datetime(2026, 11, 15, 20, tzinfo=dt.timezone.utc)


def leg(i: int, game: int, prob: float, ev: float = 5.0, odds: int = -300, model: float | None = None) -> dict:
    model = prob if model is None else model
    return {"Leg": f"P{i} · Over 9.5 points", "Stat": "Points", "stat_key": "points",
            "Game": f"G{game}", "Player": f"P{i}", "Side": "Over", "Odds": odds,
            "Model %": model * 100, "Market %": prob * 100, "prob": prob, "Leg EV %": ev,
            "player_id": i, "event_id": f"e{game}", "is_over": True, "line": 9.5}


def board(games: int = 6, per_game: int = 3) -> pd.DataFrame:
    rows = [leg(g * 10 + k, g, .9 - .01 * (g * per_game + k)) for g in range(games) for k in range(per_game)]
    return pd.DataFrame(rows)


def test_takes_the_likeliest_legs_two_a_game_one_a_player():
    table = board()
    slip = nba_parlay.long_shot_slip(table).iloc[0]
    chosen = table.loc[slip["bets"]]
    assert slip["Legs"] == 10 and len(chosen) == 10
    assert chosen.groupby("event_id").size().max() == 2
    assert chosen["player_id"].is_unique
    assert set(chosen["prob"]) == set(table.groupby("event_id").head(2).sort_values("prob").tail(10)["prob"])
    assert slip["Pays"] > 10 and 0 < slip["Chance %"] < 100


def test_needs_enough_legs_and_skips_unworthy_ones():
    assert nba_parlay.long_shot_slip(board(games=3)).empty          # 3 games, 2 a game: 6 < 8
    eight = board(games=4)
    assert nba_parlay.long_shot_slip(eight).iloc[0]["Legs"] == 8
    no_value = eight.assign(**{"Leg EV %": 0.0})
    assert nba_parlay.long_shot_slip(no_value).empty


def test_bench_locks_are_left_out():
    table = board()
    bench = frozenset(table.nlargest(2, "prob")["player_id"].astype(int))   # both are 70%+ locks
    chosen = table.loc[nba_parlay.long_shot_slip(table, bench=bench).iloc[0]["bets"]]
    assert not chosen["player_id"].isin(bench).any()


def payload(n: int = 8, per_game: int = 2, **changes) -> dict:
    legs = [{"player_id": i, "event_id": f"e{i // per_game}", "tip": "2026-11-16T00:00:00Z",
             "game": f"G{i // per_game}", "stat": "points", "side": "Over", "line": 9.5,
             "odds": -300, "evidence": {"eligible": True}} for i in range(n)]
    return {"day": "2026-11-15", "legs": legs, "payout": 1.33 ** n, "probability": .1,
            "market_probability": 1 / 1.33 ** n, "style": "Long shot", "model": "context-v2",
            "book": "kalshi", "game": None} | changes


def test_long_shot_trial_records_its_first_slip_of_the_day_apart_from_higher_hit():
    first = sr.archive(payload(), NOW, experiment=sr.LONG_SHOT_EXPERIMENT["id"])
    assert first is not None
    sr.archive(payload(n=10), NOW, experiment=sr.LONG_SHOT_EXPERIMENT["id"])
    with sr.connect() as db:
        assert db.execute("SELECT trial, offer FROM experiment").fetchall() == [(sr.LONG_SHOT_EXPERIMENT["id"], first)]
    facts = sr.summary()
    assert facts["long_shot"]["offered"] == 1 and facts["experiment"]["offered"] == 0
    assert facts["long_shot_protocol"]["id"] == sr.LONG_SHOT_EXPERIMENT["id"]


def test_long_shot_revision_records_separately_from_the_saved_trial():
    previous = sr.archive(payload(), NOW)
    with sr.connect() as db:
        db.execute("INSERT INTO experiment VALUES (?, ?, ?)", ("long-shot-v1", "2026-11-15", previous))
    current = sr.archive(payload(n=10), NOW, experiment=sr.LONG_SHOT_EXPERIMENT["id"])
    assert current and current != previous
    record = sr.summary()
    assert record["long_shot"]["offered"] == record["long_shot_previous"]["offered"] == 1
    assert record["long_shot_protocol"]["id"] == "long-shot-v2"
    assert record["long_shot_previous_protocol"]["id"] == "long-shot-v1"


@pytest.mark.parametrize("bad", [payload(n=7), payload(n=11), payload(per_game=3), payload(book="fanduel"),
                                 payload(game="G1")])
def test_long_shot_trial_rejects_slips_outside_its_rules(bad):
    assert sr.archive(bad, NOW, experiment=sr.LONG_SHOT_EXPERIMENT["id"]) is None


def test_an_ineligible_leg_keeps_the_slip_out_of_the_trial():
    bad = payload()
    bad["legs"][0]["evidence"] = {"eligible": False}
    assert sr.archive(bad, NOW, experiment=sr.LONG_SHOT_EXPERIMENT["id"]) is None


def test_the_kalshi_long_shot_offer_goes_to_its_trial(monkeypatch):
    seen = []
    monkeypatch.setattr(ss.suggested_record, "archive", lambda p, now, experiment=False: seen.append(experiment))
    table = board().assign(Game="G", tip="2026-11-16T00:00:00Z",
                           quality=[{"eligible": True}] * 18)
    chosen = {"date": "2026-11-15", "book": "kalshi", "model": "context-v2"}
    ss.archive_idea(chosen, "Long shot", None, table, list(table.index[:8]), .1, 9.0, NOW)
    ss.archive_idea(chosen | {"book": "fanduel"}, "Long shot", None, table, list(table.index[:8]), .1, 9.0, NOW)
    assert seen == [sr.LONG_SHOT_EXPERIMENT["id"], False]


def test_nightly_capture_runs_both_trials_even_when_one_fails(monkeypatch):
    from edgefinder.api import service
    calls = []

    def ideas(*args):
        calls.append(args[1:])
        if args[3] == "Higher hit rate":
            raise RuntimeError("board failed")
    monkeypatch.setattr(service, "ideas", ideas)
    ss.capture_nightly()
    assert calls == [("fanduel", "context-v2", "Higher hit rate"), ("kalshi", "context-v2", "Long shot")]


def test_the_api_builds_a_long_shot_but_not_for_one_game(monkeypatch):
    from edgefinder.api import service
    table = board().assign(quality=[{"eligible": True}] * 18)
    monkeypatch.setattr(service, "candidates", lambda *a: (table, {"date": "2026-11-15", "book": "kalshi",
                                                                   "model": "context-v2"}))
    monkeypatch.setattr(service, "_averages", dict)
    monkeypatch.setattr(service.suggestion_service, "archive_idea", lambda *a: None)
    service.clear_cache()
    [idea] = service.ideas("2026-11-15", "kalshi", "context-v2", "Long shot")
    assert len(idea["legs"]) == 10
    assert service.ideas("2026-11-15", "kalshi", "context-v2", "Long shot", game="G1") == []
