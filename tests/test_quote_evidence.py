import pandas as pd

from edgefinder.tracking import quote_evidence as qe

NOW = pd.Timestamp("2026-11-15T20:00:00Z")
ROW = pd.Series({"date": "2026-11-15", "player_id": 1, "stat_key": "points", "Side": "Over",
                 "line": 20.5, "Odds": -110, "event_id": "e1", "Player": "A"})


def history():
    return pd.DataFrame({"player_id": [1]*10, "game_date": pd.date_range("2026-11-01",periods=10),
                         "minutes": [30.0]*10, "pts": [21]*10})


def test_history_only_uses_games_before_the_projected_date():
    h = pd.concat([history(),pd.DataFrame({"player_id":[1],"game_date":[pd.Timestamp("2026-11-15")],
                                         "minutes":[1],"pts":[0]})],ignore_index=True)
    result = qe.assess(ROW,h,NOW,NOW)
    assert result["eligible"] and result["history_games"] == 10 and result["recent_hit_pct"] == 100


def test_missing_stale_and_unstable_inputs_explain_why_to_pass():
    assert not qe.assess(ROW,pd.DataFrame(),None,NOW)["eligible"]
    assert not qe.assess(ROW,history(),NOW-pd.Timedelta(hours=2),NOW)["eligible"]
    h=history().assign(minutes=[5,40]*5)
    assert "Minutes have been unstable" in qe.assess(ROW,h,NOW,NOW)["warnings"]


def test_comparison_never_calls_different_lines_or_stale_prices_a_better_payout():
    def snapshots(line=20.5, stamp="2026-11-15T19:50:00Z"):
        return pd.DataFrame([{"event_id":"e1","player":"A","line":line,"over_odds":120,
                              "under_odds":-140,"fetched_at":stamp}])
    tip = "2026-11-16T00:00:00Z"
    assert qe.comparisons(ROW,snapshots(),NOW,tip)[0]["better_payout"]
    assert not qe.comparisons(ROW,snapshots(line=21.5),NOW,tip)[0]["better_payout"]
    assert qe.comparisons(ROW,snapshots(stamp="2026-11-15T18:00:00Z"),NOW,tip)[0]["stale"]
    assert qe.comparisons(ROW,snapshots(stamp="2026-11-16T00:01:00Z"),NOW,tip) == []


def test_uncertain_quotes_are_filtered_before_the_higher_hit_search(monkeypatch):
    from edgefinder.api import service
    from edgefinder.tracking import nba_parlay
    table = pd.DataFrame([{"quality": {"eligible": False}, "Game": "A @ B", "Odds": -110, "prob": .6}], index=[1])
    chosen = {"date": "2026-11-15", "book": "fanduel", "model": "context-v2"}
    monkeypatch.setattr(service, "candidates", lambda *args: (table, chosen))
    monkeypatch.setattr(service, "_averages", dict)
    def search(pool, **kwargs):
        assert pool.empty
        assert kwargs["max_legs"] == 2 and kwargs["min_chance"] == .6
        return pd.DataFrame()
    monkeypatch.setattr(nba_parlay, "suggest_parlays", search)
    service.clear_cache()
    assert service.ideas(chosen["date"], chosen["book"], chosen["model"], "Higher hit rate") == []
    service.clear_cache()


def test_missing_minutes_and_stat_history_cannot_pass_the_quality_gate():
    assert not qe.assess(ROW,history().assign(minutes=float('nan')),NOW,NOW)["eligible"]
    assert not qe.assess(ROW,history().drop(columns='pts'),NOW,NOW)["eligible"]


def test_suggestion_cache_invalidates_when_probability_changes_without_an_odds_move(monkeypatch):
    from edgefinder.api import service, suggestion_service
    from edgefinder.tracking import nba_parlay
    table = pd.DataFrame([{"quality": {"eligible": True}, "Game": "A @ B", "Odds": -110,
                           "prob": .65}], index=[1])
    chosen = {"date": "2026-11-15", "book": "fanduel", "model": "context-v2"}
    monkeypatch.setattr(service, "candidates", lambda *args: (table, chosen))
    monkeypatch.setattr(service, "_averages", dict)
    monkeypatch.setattr(suggestion_service, "archive_idea", lambda *args: None)
    calls = []
    def search(pool, **kwargs):
        calls.append(float(pool.iloc[0]["prob"]))
        return pd.DataFrame([{"bets": [1], "Chance %": calls[-1]*100, "Pays": 1, "EV %": 1}])
    monkeypatch.setattr(nba_parlay, "suggest_parlays", search)
    service.clear_cache()
    assert service.ideas(None,None,None,"Higher hit rate")[0]["chance_pct"] == 65
    table.loc[1,"prob"] = .75
    assert service.ideas(None,None,None,"Higher hit rate")[0]["chance_pct"] == 75
    assert calls == [.65,.75]
    service.clear_cache()
