import pytest

from edgefinder.tracking import nba_paper, nba_recording

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
LINES = [
    {"player": "Cade Cunningham", "line": 24.5, "over_odds": -110, "under_odds": -110},
    {"player": "Joel Embiid", "line": 28.5, "over_odds": -115, "under_odds": -105},
]
RECORDED_AT = "2026-11-04T17:00:00+00:00"
GAME_DATE = "2026-11-04"


def projector(means):
    def project(event, names):
        return {name: {"player_id": index, "mean": means[name]}
                for index, name in enumerate(names, start=1) if name in means}
    return project


def model(version, means, dispersion=7.8):
    return nba_recording.RegisteredModel(version, dispersion, projector(means))


def record(models, path):
    return nba_recording.record_event(
        EVENT, LINES, models, RECORDED_AT, GAME_DATE, path=path)


def test_each_registered_model_gets_its_own_rows_for_the_same_lines(tmp_path):
    path = tmp_path / "log.csv"
    added = record([
        model("champion", {"Cade Cunningham": 25.0, "Joel Embiid": 29.0}),
        model("challenger", {"Cade Cunningham": 27.0, "Joel Embiid": 27.0}),
    ], path)
    assert added == {"champion": 2, "challenger": 2}
    ledger = nba_paper.load_ledger(path=path)
    assert sorted(ledger["model_version"].unique()) == ["challenger", "champion"]
    assert len(ledger) == 4


def test_a_model_that_fails_does_not_block_the_others(tmp_path):
    path = tmp_path / "log.csv"

    def broken(event, names):
        raise RuntimeError("could not train")

    added = record([
        nba_recording.RegisteredModel("broken", 7.8, broken),
        model("champion", {"Cade Cunningham": 25.0}),
    ], path)
    assert added == {"broken": 0, "champion": 1}
    assert list(nba_paper.load_ledger(path=path)["model_version"]) == ["champion"]


def test_recording_the_same_game_twice_adds_nothing(tmp_path):
    path = tmp_path / "log.csv"
    models = [model("champion", {"Cade Cunningham": 25.0})]
    record(models, path)
    assert record(models, path) == {"champion": 0}


def test_a_new_model_can_be_added_for_a_game_that_was_already_recorded(tmp_path):
    path = tmp_path / "log.csv"
    record([model("champion", {"Cade Cunningham": 25.0})], path)
    added = record([model("champion", {"Cade Cunningham": 25.0}),
                    model("challenger", {"Cade Cunningham": 26.0})], path)
    assert added == {"champion": 0, "challenger": 1}


def test_each_model_uses_its_own_dispersion(tmp_path):
    path = tmp_path / "log.csv"
    record([model("tight", {"Cade Cunningham": 30.0}, dispersion=50.0),
            model("wide", {"Cade Cunningham": 30.0}, dispersion=2.0)], path)
    ledger = nba_paper.load_ledger(path=path).set_index("model_version")
    assert ledger.loc["tight", "model_p_over"] > ledger.loc["wide", "model_p_over"]
