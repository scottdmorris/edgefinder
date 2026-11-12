"""Games past the Odds API budget still get Kalshi's free prices, once early and once late."""

import datetime as dt

import pandas as pd

from edgefinder.data import nba_snapshot_plan as plan

UTC = dt.timezone.utc


def event(event_id: str, tip_utc: str) -> dict:
    return {"event_id": event_id, "commence_time": tip_utc,
            "home": f"{event_id} home", "away": f"{event_id} away"}


def snaps(*pairs):
    return pd.DataFrame(pairs, columns=["event_id", "phase"])


def planned(tasks):
    return [(task.event["event_id"], task.phase) for task in tasks]


# Two games already used the budget of two; g2 tips 10pm ET (03:00Z), g3 10:30pm ET.
EVENTS = [event("g0", "2026-11-05T00:00:00Z"), event("g1", "2026-11-05T00:30:00Z"),
          event("g2", "2026-11-05T03:00:00Z"), event("g3", "2026-11-05T03:30:00Z")]
TAKEN = snaps(("g0", "early"), ("g1", "early"))
SEVEN_PM_ET = dt.datetime(2026, 11, 5, 0, 0, tzinfo=UTC)       # g2 is 180 min away, g3 210


def kalshi(now, priced=(), closed=(), snapshots=TAKEN, max_games=2):
    return planned(plan.plan_kalshi_only(EVENTS, snapshots, now, set(priced), set(closed),
                                         max_games=max_games))


def test_games_past_the_budget_are_recorded_from_kalshi_in_their_early_window():
    assert kalshi(SEVEN_PM_ET) == [("g2", "early"), ("g3", "early")]


def test_a_game_already_priced_from_kalshi_is_not_recorded_again():
    assert kalshi(SEVEN_PM_ET, priced={"g2"}) == [("g3", "early")]


def test_a_game_the_fanduel_snapshot_covers_or_is_about_to_cover_is_left_to_it():
    assert kalshi(SEVEN_PM_ET, max_games=3) == [("g3", "early")]      # g2 takes the third slot
    everything = snaps(("g0", "early"), ("g1", "early"), ("g2", "early"), ("g3", "early"))
    assert kalshi(SEVEN_PM_ET, snapshots=everything, max_games=4) == []


def test_nothing_is_recorded_too_early_or_after_the_early_window_without_a_first_price():
    noon = dt.datetime(2026, 11, 4, 17, 0, tzinfo=UTC)
    assert kalshi(noon) == []
    nine_pm = dt.datetime(2026, 11, 5, 2, 0, tzinfo=UTC)              # g2 is 60 min away
    assert ("g2", "early") not in kalshi(nine_pm)


def test_a_priced_game_gets_one_closing_snapshot_before_tip():
    nine_pm = dt.datetime(2026, 11, 5, 2, 0, tzinfo=UTC)
    assert kalshi(nine_pm, priced={"g2", "g3"}) == [("g2", "late"), ("g3", "late")]
    assert kalshi(nine_pm, priced={"g2", "g3"}, closed={"g2"}) == [("g3", "late")]
    assert kalshi(nine_pm, priced={"g3"}) == [("g3", "late")]          # no close without a pick price


def test_tomorrows_games_and_games_already_tipped_are_ignored():
    after_tip = dt.datetime(2026, 11, 5, 3, 10, tzinfo=UTC)
    assert ("g2", "late") not in kalshi(after_tip, priced={"g2"})
    tomorrow = [event("t", "2026-11-06T00:30:00Z")]
    assert plan.plan_kalshi_only(tomorrow, snaps(), SEVEN_PM_ET, set(), set()) == []
