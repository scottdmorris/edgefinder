import datetime as dt
import json

import pandas as pd
import pytest

from edgefinder.tracking import suggested_record as sr
from game_log_helpers import complete_game

NOW = dt.datetime(2026, 11, 15, 20, tzinfo=dt.timezone.utc)


def offer(**changes):
    legs = [{"player_id": p, "tip": "2026-11-16T00:00:00Z", "game": "Philadelphia 76ers @ Detroit Pistons",
             "stat": "points", "side": "Over", "line": 9.5, "odds": -200} for p in [1, 2]]
    return {"day": "2026-11-15", "legs": legs, "payout": 2.25, "probability": .6,
            "market_probability": 1/2.25, "style": "Balanced"} | changes


def games(a=15, b=12):
    return pd.DataFrame({"player_id": [1, 2], "game_date": pd.to_datetime(["2026-11-15"]*2), "pts": [a,b]})


def test_identical_offers_deduplicate_and_preserve_the_first_timestamp():
    first = sr.archive(offer(), NOW)
    assert sr.archive(offer(), NOW + dt.timedelta(minutes=1)) == first
    with sr.connect() as db:
        rows = db.execute("SELECT payload FROM offers").fetchall()
    assert len(rows) == 1 and json.loads(rows[0][0])["recorded_at"] == NOW.isoformat()


def test_after_tip_is_never_backfilled():
    assert sr.archive(offer(), NOW + dt.timedelta(hours=5)) is None
    assert sr.summary()["offered"]["offered"] == 0


@pytest.mark.parametrize("values, units, wins", [((15,12),1.25,1), ((3,12),-1,0)])
def test_grade_payout_and_hits_from_the_actual_frozen_slip(values, units, wins):
    sr.archive(offer(), NOW)
    assert sr.grade(games(*values), dt.date(2026,11,16)) == 1
    assert sr.grade(games(*values), dt.date(2026,11,16)) == 0
    facts = sr.summary()["offered"]
    assert facts["units"] == units and facts["wins"] == wins and facts["graded"] == 1
    assert facts["brier"] == pytest.approx((.6-wins)**2)


def test_partial_logs_wait_and_voided_leg_reduces_payout_and_excludes_calibration():
    sr.archive(offer(), NOW)
    assert sr.grade(games().iloc[:1], dt.date(2026,11,16)) == 0
    full = pd.concat([complete_game("2026-11-15"), games().iloc[:1]],ignore_index=True)
    assert sr.grade(full, dt.date(2026,11,16)) == 1
    facts = sr.summary()["offered"]
    assert facts["units"] == .5 and facts["calibration_n"] == 0


def test_first_experiment_offer_of_the_day_cannot_be_replaced_by_later_prices():
    trial = offer(model="context-v2", book="fanduel", style="Higher hit rate")
    for index, leg in enumerate(trial["legs"]):
        leg.update(event_id=f"e{index}", evidence={"eligible": True})
    first = sr.archive(trial, NOW, experiment=True)
    assert first is not None
    sr.archive(trial | {"payout": 2.5}, NOW, experiment=True)
    with sr.connect() as db:
        assert db.execute("SELECT offer FROM experiment").fetchone()[0] == first


def test_protocol_change_blocks_new_trial_entries_but_not_reading_or_grading(monkeypatch):
    trial = offer(model="context-v2", book="fanduel", style="Higher hit rate")
    for index, leg in enumerate(trial["legs"]):
        leg.update(event_id=f"e{index}", evidence={"eligible": True})
    sr.archive(trial, NOW, experiment=True)
    monkeypatch.setitem(sr.EXPERIMENT, "min_joint_probability", .7)
    with pytest.raises(ValueError, match="rules changed"):
        sr.archive(trial | {"payout": 3.0}, NOW, experiment=True)
    assert sr.summary()["protocol"]["min_joint_probability"] == .6
    assert sr.grade(games(), dt.date(2026,11,16)) == 1
    assert sr.summary()["experiment"]["wins"] == 1


def test_ineligible_trial_cannot_be_recorded_by_bypassing_the_search():
    assert sr.archive(offer(), NOW, experiment=True) is None


@pytest.mark.parametrize("spec", [sr.EXPERIMENT, sr.LONG_SHOT_EXPERIMENT])
def test_indexed_quote_lookups_accept_only_the_verified_previous_fingerprint(spec, monkeypatch):
    with sr.connect() as db:
        sr.freeze_protocol(db, spec)
        protocol = json.loads(db.execute("SELECT payload FROM protocol").fetchone()[0])
        protocol["recipe_sha256"]["suggestion_service.py"] = sr._PRE_INDEXED_QUOTES
        previous = json.dumps(protocol, sort_keys=True)
        db.execute("UPDATE protocol SET payload=?", (previous,))
        sr.freeze_protocol(db, spec)
        assert db.execute("SELECT payload FROM protocol").fetchone()[0] == previous
        monkeypatch.setattr(sr, "_INDEXED_QUOTES", "unrecognized recipe")
        with pytest.raises(ValueError, match="rules changed"):
            sr.freeze_protocol(db, spec)


def test_reordered_legs_are_the_same_offer_not_an_extra_win_opportunity():
    payload = offer()
    first = sr.archive(payload, NOW)
    assert sr.archive(payload | {"legs": list(reversed(payload["legs"]))}, NOW) == first
    assert sr.summary()["offered"]["offered"] == 1
