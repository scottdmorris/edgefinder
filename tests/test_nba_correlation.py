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
            for _ in range(3):
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


def simulated_pair(same: float, teammate: float, opponent: float, games: int = 4000, seed: int = 3):
    """Two stats for six players a game with known cross-correlations: a player's two
    stats share `same`, a team's players share `teammate` across stats, the game shares
    `opponent`."""
    rng = np.random.default_rng(seed)
    a_rows, b_rows = [], []
    pid = 0
    for game_id in range(games):
        game_lift = rng.normal() * np.sqrt(opponent)
        for team in ("AAA", "BBB"):
            team_lift = rng.normal() * np.sqrt(max(teammate - opponent, 0.0))
            for _ in range(3):
                pid += 1
                shared = rng.normal() * np.sqrt(max(same - teammate, 0.0))
                za = game_lift + team_lift + shared + rng.normal() * np.sqrt(1 - same)
                zb = game_lift + team_lift + shared + rng.normal() * np.sqrt(1 - same)
                a_rows.append({"game_id": game_id, "team": team, "player_id": pid, "z": za})
                b_rows.append({"game_id": game_id, "team": team, "player_id": pid, "z": zb})
    return pd.DataFrame(a_rows), pd.DataFrame(b_rows)


def test_cross_stat_correlations_recover_the_known_values():
    a, b = simulated_pair(same=0.5, teammate=0.2, opponent=0.1)
    result = nba_correlation.cross_pair_correlations(a, b)
    assert result["same_player"] == pytest.approx(0.5, abs=0.04)
    assert result["teammate"] == pytest.approx(0.2, abs=0.04)
    assert result["opponent"] == pytest.approx(0.1, abs=0.04)


def test_independent_stats_show_no_cross_correlation_and_the_pair_counts_are_right():
    a, b = simulated_pair(same=0.0, teammate=0.0, opponent=0.0, games=2000)
    result = nba_correlation.cross_pair_correlations(a, b)
    assert max(abs(result["same_player"]), abs(result["teammate"]),
               abs(result["opponent"])) < 0.04
    # per game: 6 players; each team has 3*2 = 6 ordered teammate pairs; opponents 2*3*3 = 18
    assert result["same_player_pairs"] == 2000 * 6
    assert result["teammate_pairs"] == 2000 * 2 * 6 and result["opponent_pairs"] == 2000 * 18


def test_only_players_with_both_stats_count_and_no_overlap_is_zero():
    a, b = simulated_pair(same=0.5, teammate=0.2, opponent=0.1, games=50)
    assert nba_correlation.cross_pair_correlations(a, b.assign(player_id=b["player_id"] + 10**6))[
        "same_player_pairs"] == 0
    half = nba_correlation.cross_pair_correlations(a, b[b["player_id"] % 2 == 0])
    assert half["same_player_pairs"] == 50 * 3
