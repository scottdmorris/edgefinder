import datetime as dt

import pandas as pd

from edgefinder.api import suggestion_service as ss
from edgefinder.tracking import nba_alt, nba_parlay, suggested_record
from test_api import DAY, _ledger

NOW = dt.datetime(2026,11,4,20,tzinfo=dt.timezone.utc)
CHOSEN = {"date": DAY, "book": "fanduel", "model": "minutes-v1"}


def table():
    ledger = _ledger()
    return nba_parlay.all_candidates(ledger, pd.DataFrame(columns=nba_alt.COLUMNS), DAY,
                                    "minutes-v1", "fanduel", nba_parlay.sources(ledger, DAY)), ledger


def history():
    return pd.DataFrame([{"player_id": p, "game_date": day, "pts": 30, "minutes": 30}
                         for p in [1,2] for day in pd.date_range('2026-10-24',periods=10)])


def snapshots(line=24.5):
    return pd.DataFrame([{"event_id": "e1", "player": "Jaylen Brown", "line": line,
                          "over_odds": 110, "under_odds": -130, "fetched_at": '2026-11-04T19:55:00Z'}])


def test_latest_archived_price_refreshes_quote_and_moved_number_blocks_suggestion(monkeypatch):
    pool, ledger = table()
    monkeypatch.setattr(ss.nba_props, 'load_snapshots', snapshots)
    monkeypatch.setattr(ss.nba_props, 'load_book_snapshots', lambda: snapshots(25.5))
    out = ss.enrich(pool, CHOSEN, ledger, pd.DataFrame(), history(), NOW)
    row = out[(out.player_id==1)&(out.Side=='Over')].iloc[0]
    assert row['Odds']==110 and row.quality['eligible']
    from edgefinder.betting.odds_math import devig_two_way, implied_prob
    import pytest
    fair = devig_two_way(implied_prob(110), implied_prob(-130))[0]
    assert row['prob'] == pytest.approx(.3 * row['Model %']/100 + .7 * fair)
    assert row['Leg EV %'] == pytest.approx((row['prob'] * 2.1 - 1) * 100)
    assert row.comparisons[0]['same_line'] is False
    assert row.quality['price_at']=='2026-11-04T19:55:00+00:00'
    monkeypatch.setattr(ss.nba_props, 'load_snapshots', lambda: snapshots(25.5))
    moved = ss.enrich(pool, CHOSEN, ledger, pd.DataFrame(), history(), NOW)
    assert not moved[moved.player_id==1].iloc[0].quality['eligible']


def test_archiving_an_offer_keeps_the_original_odds_and_probability(monkeypatch):
    pool, ledger = table()
    monkeypatch.setattr(ss.nba_props, 'load_snapshots', snapshots)
    monkeypatch.setattr(ss.nba_props, 'load_book_snapshots', pd.DataFrame)
    out = ss.enrich(pool, CHOSEN, ledger, pd.DataFrame(), history(), NOW)
    ids = out[out.Side=='Over'].index.tolist()
    assert ss.archive_idea(CHOSEN,'Balanced',None,out,ids,.65,2.3,NOW)
    assert suggested_record.summary()['offered']['offered']==1
    with suggested_record.connect() as db:
        import json
        frozen=json.loads(db.execute('SELECT payload FROM offers').fetchone()[0])
    assert frozen['probability']==.65 and next(leg for leg in frozen['legs'] if leg['player_id']==1)['odds']==110


def test_nightly_trial_does_not_request_another_book_or_model(monkeypatch):
    from edgefinder.api import service
    calls=[]
    monkeypatch.setattr(service,'ideas',lambda *args: calls.append(args))
    ss.capture_nightly()
    assert calls[0][1:]==('fanduel','context-v2','Higher hit rate')


def test_one_sided_refresh_cannot_qualify_using_an_old_market_probability(monkeypatch):
    pool, ledger = table()
    monkeypatch.setattr(ss.nba_props, 'load_snapshots', lambda: snapshots().assign(under_odds=None))
    monkeypatch.setattr(ss.nba_props, 'load_book_snapshots', pd.DataFrame)
    out = ss.enrich(pool, CHOSEN, ledger, pd.DataFrame(), history(), NOW)
    row = out[(out.player_id==1)&(out.Side=='Over')].iloc[0]
    assert not row.quality['eligible']
    assert 'Two-sided market price unavailable' in row.quality['warnings']
