import datetime as dt

from edgefinder import pipeline


def _iso(delta_hours: float) -> str:
    when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=delta_hours)
    return when.isoformat().replace("+00:00", "Z")


def _event(commence: str, home="H", away="A", home_ml=-120):
    return {
        "home": home, "away": away, "commence_time": commence,
        "home_ml": home_ml, "away_ml": 100, "total_line": 8.5,
        "over_odds": -110, "under_odds": -110,
    }


def test_started_games_are_dropped():
    index = pipeline._index_odds([_event(_iso(-2))])
    assert index == {}


def test_upcoming_games_are_kept():
    index = pipeline._index_odds([_event(_iso(3))])
    assert ("H", "A") in index


def test_match_picks_closest_start_time():
    tonight = _event(_iso(2), home_ml=-150)
    tomorrow = _event(_iso(26), home_ml=-110)
    match = pipeline._match_event([tonight, tomorrow], _iso(25.5))
    assert match["home_ml"] == -110


def test_match_rejects_events_outside_window():
    tomorrow_only = _event(_iso(26))
    assert pipeline._match_event([tomorrow_only], _iso(2)) is None


def test_no_candidates_returns_none():
    assert pipeline._match_event([], _iso(2)) is None
