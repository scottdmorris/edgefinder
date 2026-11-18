"""Fresh comparisons must remain serializable, including numeric pandas prices."""
import json

import pandas as pd

from edgefinder.tracking import quote_evidence


def test_fresh_better_payout_is_a_json_boolean():
    row = pd.Series({"stat_key": "points", "event_id": "e1", "Player": "A",
                     "Side": "Over", "line": 20.5, "Odds": -110})
    snapshots = pd.DataFrame([{"event_id": "e1", "player": "A", "line": 20.5,
                               "fetched_at": "2026-11-17T20:00:00Z",
                               "over_odds": -105, "under_odds": -115}])
    found = quote_evidence.comparisons(row, snapshots, pd.Timestamp("2026-11-17T20:30:00Z"),
                                       "2026-11-18T00:00:00Z")
    assert found[0]["better_payout"] is True
    assert json.loads(json.dumps(found))[0]["better_payout"] is True
