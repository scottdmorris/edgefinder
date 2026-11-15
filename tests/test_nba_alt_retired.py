"""The two oldest models still price every X+ line, so the record keeps judging them, but
they no longer make X+ picks: over their first 1,250 graded X+ picks they returned about
-25%, against about -6% for the context models."""

import pytest

from edgefinder.tracking import nba_alt
from test_nba_alt import EVENT, LINES, PREDICTIONS


def priced(version):
    return {r["threshold"]: r for r in nba_alt.build_alt_rows(
        EVENT, LINES, PREDICTIONS, "2026-11-04T17:00:00+00:00", "2026-11-04",
        model_version=version, dispersion=7.8)}


@pytest.mark.parametrize("version", ["ewma-v1", "minutes-v1"])
def test_a_retired_model_still_prices_the_line_but_never_picks_it(version):
    row = priced(version)[25]
    assert row["model_p"] > row["market_p"]          # the same price IS a pick for others
    assert not row["is_pick"] and row["pick_ev"] is None


@pytest.mark.parametrize("version", ["context-v1", "context-v2"])
def test_the_context_models_still_make_x_plus_picks(version):
    row = priced(version)[25]
    assert row["is_pick"] and row["pick_ev"] >= nba_alt.MIN_EV_TO_RECORD


def test_the_retired_list_names_only_models_that_exist():
    assert nba_alt.NO_X_PLUS_PICKS == {"ewma-v1", "minutes-v1"}
    assert nba_alt.NO_X_PLUS_PICKS <= set(nba_alt.DISPERSIONS)
