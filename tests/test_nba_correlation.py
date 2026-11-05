import numpy as np
import pandas as pd
import pytest

from edgefinder.models import nba_correlation


def simulated_games(teammate_shift: float, opponent_shift: float, games: int = 3000,
                    seed: int = 1) -> pd.DataFrame:
    """Two teams of three starters. Each game has a shared lift for each team
    and a lift for the whole game, so the true correlations are known."""
    rng = np.random.default_rng(seed)
    rows = []
    for game_id in range(games):
        game_lift = rng.normal() * opponent_shift
        for team in ("AAA", "BBB"):
            team_lift = rng.normal() * teammate_shift
            for player in range(3):
                noise = rng.normal()
                z = game_lift + team_lift + noise
                rows.append({"game_id": game_id, "team": team, "pred_ewma": 20.0,
                             "n_prior": 30, "pts": 20.0 + z * np.sqrt(20 + 400 / 7.8)})
    return pd.DataFrame(rows)


def test_independent_players_show_no_correlation():
    misses = nba_correlation.standardised_misses(simulated_games(0.0, 0.0), 7.8)
    result = nba_correlation.pair_correlations(misses)
    assert result["teammate"] == pytest.approx(0.0, abs=0.03)
    assert result["opponent"] == pytest.approx(0.0, abs=0.03)


def test_a_shared_game_lift_shows_up_as_correlation_between_opponents_and_teammates():
    misses = nba_correlation.standardised_misses(simulated_games(0.0, 0.5), 7.8)
    result = nba_correlation.pair_correlations(misses)
    # variance 1.25 total, 0.25 of it shared by everyone in the game: r = 0.2
    assert result["opponent"] == pytest.approx(0.2, abs=0.03)
    assert result["teammate"] == pytest.approx(0.2, abs=0.03)


def test_a_team_only_lift_correlates_teammates_but_not_opponents():
    misses = nba_correlation.standardised_misses(simulated_games(0.8, 0.0), 7.8)
    result = nba_correlation.pair_correlations(misses)
    assert result["teammate"] > 0.25
    assert result["opponent"] == pytest.approx(0.0, abs=0.03)


def test_pair_counts_match_the_roster_sizes():
    result = nba_correlation.pair_correlations(
        nba_correlation.standardised_misses(simulated_games(0.0, 0.0, games=10), 7.8))
    assert result["teammate_pairs"] == 10 * 2 * 3      # 3 pairs per team, 2 teams
    assert result["opponent_pairs"] == 10 * 3 * 3


def test_bench_players_and_thin_histories_are_left_out():
    games = simulated_games(0.0, 0.0, games=5)
    games.loc[games.index[:6], "pred_ewma"] = 4.0         # a whole team of bench players
    games.loc[games.index[6:9], "n_prior"] = 2            # thin history
    misses = nba_correlation.standardised_misses(games, 7.8)
    assert len(misses) == len(games) - 9
