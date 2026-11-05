"""Run the app with the live NBA feed replaced by canned games (for screenshots).

Used with scripts/make_demo_data.py on a copy of the repo; see that file.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from edgefinder.data import nba_live  # noqa: E402

GAMES = [
    nba_live.LiveGame("g1", 2, "Q3 4:12", 3, "4:12", "BOS", "NYK", 78, 81),
    nba_live.LiveGame("g2", 1, "7:30 pm ET", 0, "", "DEN", "LAL", 0, 0),
    nba_live.LiveGame("g3", 3, "Final", 4, "", "PHI", "MIL", 104, 112),
]
nba_live.fetch_games = lambda: GAMES
nba_live.fetch_box = lambda game_id: {
    1001 + i: nba_live.PlayerLine(1001 + i, n, t, 12 + i, 4, 3, 22.0, True, i < 2, True)
    for i, (n, t) in enumerate([("Jalen Brunson", "NYK"), ("Jayson Tatum", "BOS")])}
nba_live.fetch_plays = lambda *a, **k: []
nba_live.fetch_detail = lambda gid, away, home: nba_live.GameDetail(
    nba_live.fetch_box(gid), {}, {}, [], [])

import runpy  # noqa: E402

runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
