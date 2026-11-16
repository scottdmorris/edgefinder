"""Complete regulation player logs, including both teams, for settlement tests."""
import pandas as pd


def complete_game(day="2026-11-04", home="DET", away="PHI"):
    return pd.DataFrame([{"player_id": 100 + n + side * 5, "game_date": pd.Timestamp(day),
                          "game_id": "finished", "team": team, "opponent": opponent,
                          "minutes": 48.0, "pts": 10.0}
                         for side, (team, opponent) in enumerate(((home, away), (away, home)))
                         for n in range(5)])
