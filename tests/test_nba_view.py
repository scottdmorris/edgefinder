import pandas as pd
import pytest

from edgefinder.tracking import nba_paper, nba_view

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
OTHER = {"event_id": "e2", "commence_time": "2026-11-06T00:00:00Z",
         "home": "Boston Celtics", "away": "Milwaukee Bucks"}
LINES = [
    {"player": "Cade Cunningham", "line": 24.5, "over_odds": -110, "under_odds": -110},
    {"player": "Duncan Robinson", "line": 13.5, "over_odds": -130, "under_odds": -102},
]


def rows(event, game_date, version, means, dispersion=7.8):
    predictions = {name: {"player_id": i, "mean": mean}
                   for i, (name, mean) in enumerate(means.items(), start=1)}
    return nba_paper.build_ledger_rows(
        event, LINES, predictions, "2026-11-04T17:00:00+00:00", game_date,
        model_version=version, dispersion=dispersion)


def ledger():
    data = (
        rows(EVENT, "2026-11-04", "ewma-v1", {"Cade Cunningham": 20.0, "Duncan Robinson": 13.0})
        + rows(EVENT, "2026-11-04", "minutes-v1", {"Cade Cunningham": 32.0})
        + rows(OTHER, "2026-11-05", "ewma-v1", {"Cade Cunningham": 22.0})
    )
    return pd.DataFrame(data, columns=nba_paper.COLUMNS)


def test_game_dates_are_listed_newest_first():
    assert nba_view.game_dates(ledger()) == ["2026-11-05", "2026-11-04"]


def test_there_is_one_row_per_line_with_each_models_columns_side_by_side():
    table = nba_view.lines_for_date(ledger(), "2026-11-04")
    assert len(table) == 2
    cade = table[table["Player"] == "Cade Cunningham"].iloc[0]
    assert cade["Game"] == "Philadelphia 76ers @ Detroit Pistons"
    assert cade["Line"] == 24.5
    assert cade["ewma-v1 proj"] == pytest.approx(20.0)
    assert cade["minutes-v1 proj"] == pytest.approx(32.0)
    assert cade["minutes-v1 P(over)"] > cade["ewma-v1 P(over)"]


def test_a_line_one_model_did_not_price_is_left_blank_for_that_model():
    table = nba_view.lines_for_date(ledger(), "2026-11-04")
    duncan = table[table["Player"] == "Duncan Robinson"].iloc[0]
    assert duncan["ewma-v1 proj"] == pytest.approx(13.0)
    assert pd.isna(duncan["minutes-v1 proj"])


def test_each_models_pick_side_is_shown():
    table = nba_view.lines_for_date(ledger(), "2026-11-04")
    cade = table[table["Player"] == "Cade Cunningham"].iloc[0]
    assert cade["minutes-v1 pick"] == "over"      # 32 vs 24.5: model likes the over
    assert cade["ewma-v1 pick"] in ("under", "")  # 20 vs 24.5: never the over


def test_the_market_probability_is_shared_across_models():
    table = nba_view.lines_for_date(ledger(), "2026-11-04")
    assert table["Market P(over)"].notna().all()


def test_the_gap_column_uses_the_newest_model_that_priced_the_line():
    table = nba_view.lines_for_date(ledger(), "2026-11-04").set_index("Player")
    assert table.loc["Cade Cunningham", "Gap"] == pytest.approx(32.0 - 24.5)
    assert table.loc["Duncan Robinson", "Gap"] == pytest.approx(13.0 - 13.5)


def test_a_date_with_nothing_recorded_gives_an_empty_table():
    assert nba_view.lines_for_date(ledger(), "2030-01-01").empty


def test_suggestions_list_picked_sides_best_first_with_model_agreement():
    table = nba_view.suggestions(ledger(), "2026-11-04")
    assert list(table.columns) == ["player_id", "Bet", "Game", "Odds", "Model projects",
                                   "EV %", "Agree"]
    assert set(table["player_id"]) == {1}                   # so the card can show his photo
    # the two models disagree on Cade (32 vs 20 against 24.5), so both sides are listed
    bets = set(table["Bet"])
    assert {"Cade Cunningham · Over 24.5 points",
            "Cade Cunningham · Under 24.5 points"} <= bets
    assert (table["Agree"] == 1).all()
    assert (table["EV %"] > 0).all()
    assert table["EV %"].is_monotonic_decreasing


def test_suggestions_merge_models_that_pick_the_same_side():
    data = rows(EVENT, "2026-11-04", "ewma-v1", {"Cade Cunningham": 32.0}) \
        + rows(EVENT, "2026-11-04", "minutes-v1", {"Cade Cunningham": 33.0})
    table = nba_view.suggestions(pd.DataFrame(data, columns=nba_paper.COLUMNS), "2026-11-04")
    cade = table[table["Bet"].str.contains("Cade")]
    assert len(cade) == 1 and cade.iloc[0]["Agree"] == 2


def test_suggestions_for_a_slate_with_no_picks_are_empty():
    assert nba_view.suggestions(ledger(), "2030-01-01").empty


def test_collection_status_counts_games_lines_and_settlements():
    snapshots = pd.DataFrame({
        "fetched_at": ["2026-11-04T17:00:00+00:00", "2026-11-04T17:00:00+00:00",
                       "2026-11-04T23:30:00+00:00"],
        "phase": ["early", "early", "late"],
        "event_id": ["e1", "e1", "e1"], "player": ["a", "b", "a"],
    })
    status = nba_view.collection_status(snapshots, ledger())
    assert status["games"] == 1
    assert status["lines_archived"] == 3
    assert status["ledger_rows"] == len(ledger())
    assert status["last_snapshot"] == "2026-11-04T23:30:00+00:00"
    assert status["settled"] == 0


def test_collection_status_with_no_data_is_all_zeros():
    status = nba_view.collection_status(
        pd.DataFrame(columns=["fetched_at", "phase", "event_id", "player"]),
        pd.DataFrame(columns=nba_paper.COLUMNS))
    assert status["games"] == 0 and status["lines_archived"] == 0
    assert status["last_snapshot"] is None


def settled_ledger():
    games = pd.DataFrame({"player_id": [1], "game_date": pd.to_datetime(["2026-11-04"]), "pts": [30.0]})
    empty_snapshots = pd.DataFrame(columns=["fetched_at", "phase", "event_id", "player",
                                            "line", "over_odds", "under_odds"])
    only_day_one = ledger()[ledger()["game_date"] == "2026-11-04"]
    return nba_paper.settle(only_day_one, games, empty_snapshots, pd.Timestamp("2026-11-06").date())


def test_the_scorecard_has_one_row_per_model_with_results_and_brier_scores():
    table = nba_view.scorecard(settled_ledger())
    assert list(table.index) == ["ewma-v1", "minutes-v1"]
    assert table.loc["minutes-v1", "Record"] == "1-0"        # over pick, scored 30 vs 24.5
    assert table.loc["minutes-v1", "Lines scored"] == 1
    # the 32-point projection was far closer to the 30 scored than the 20-point one
    assert table.loc["minutes-v1", "Model Brier"] < table.loc["ewma-v1", "Model Brier"]


def test_the_scorecard_for_an_unsettled_ledger_shows_zero_lines_scored():
    table = nba_view.scorecard(ledger())
    assert (table["Lines scored"] == 0).all()


def test_a_game_day_reads_the_way_people_say_it():
    import datetime as dt
    today = dt.date(2026, 11, 6)
    assert nba_view.day_label("2026-11-06", today) == "Today"
    assert nba_view.day_label("2026-11-05", today) == "Yesterday"
    assert nba_view.day_label("2026-11-07", today) == "Tomorrow"
    assert nba_view.day_label("2026-11-04", today) == "Wed, Nov 4"


def test_a_game_reads_as_team_codes():
    assert nba_view.short_game("Miami Heat @ Golden State Warriors") == "MIA @ GSW"
    assert nba_view.short_game("Nowhere FC @ Golden State Warriors") == \
        "Nowhere FC @ Golden State Warriors"
    assert nba_view.short_game("tbd") == "tbd"
