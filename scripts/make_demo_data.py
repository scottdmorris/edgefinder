"""Make a small fake data directory so every tab renders real content.

The app reads fixed paths under <repo>/data (there is no environment
variable to redirect them), so run this against a COPY of the repo:

    cp -r . /tmp/demo && rm -rf /tmp/demo/.git /tmp/demo/data
    python scripts/make_demo_data.py --root /tmp/demo
    cd /tmp/demo && streamlit run scripts/demo_app.py

Everything here is invented: players, lines, results. It exists only to
look at the screens.
"""

import argparse
import datetime as dt
import random
from pathlib import Path

import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

TEAMS = [("NYK", "BOS"), ("LAL", "DEN"), ("MIL", "PHI"), ("GSW", "DAL")]
NAMES = {
    "NYK": ["Jalen Brunson", "Karl-Anthony Towns"], "BOS": ["Jayson Tatum", "Jaylen Brown"],
    "LAL": ["Luka Doncic", "Austin Reaves"], "DEN": ["Nikola Jokic", "Jamal Murray"],
    "MIL": ["Giannis Antetokounmpo", "Damian Lillard"], "PHI": ["Tyrese Maxey", "Joel Embiid"],
    "GSW": ["Stephen Curry", "Jimmy Butler"], "DAL": ["Anthony Davis", "Kyrie Irving"],
}
MODELS = ["ewma-v1", "minutes-v1", "context-v1"]


def players() -> list[dict]:
    out, pid = [], 1000
    for team, names in NAMES.items():
        for name in names:
            pid += 1
            out.append({"player_id": pid, "player_name": name, "team": team,
                        "base": random.Random(pid).uniform(14, 32)})
    return out


def game_logs(today: dt.date) -> dict[str, pd.DataFrame]:
    rng = random.Random(7)
    seasons = {"2025-26": (dt.date(2025, 10, 22), dt.date(2026, 4, 12)),
               "2026-27": (dt.date(2026, 10, 21), today - dt.timedelta(days=1))}
    teams = list(NAMES)
    frames = {}
    for season, (start, end) in seasons.items():
        rows, day, gid = [], start, 0
        while day <= end:
            if rng.random() < 0.6:
                for p in players():
                    if rng.random() < 0.92:
                        opp = rng.choice([t for t in teams if t != p["team"]])
                        gid += 1
                        rows.append({
                            "player_id": p["player_id"], "player_name": p["player_name"],
                            "team_id": 1, "team": p["team"], "game_id": f"{season}{gid}",
                            "game_date": day.isoformat(), "matchup": f"{p['team']} vs. {opp}",
                            "wl": "W", "minutes": round(rng.uniform(26, 38), 1),
                            "pts": max(0, int(rng.gauss(p["base"], 7))),
                            "reb": max(0, int(rng.gauss(6, 3))), "ast": max(0, int(rng.gauss(5, 3))),
                            "fg3m": max(0, int(rng.gauss(2.5, 1.5))), "stl": 1, "blk": 0,
                            "tov": 2, "fga": 18, "fta": 5})
            day += dt.timedelta(days=1)
        frame = pd.DataFrame(rows)
        frame["game_date"] = pd.to_datetime(frame["game_date"])
        frame["is_home"] = True
        frame["opponent"] = frame["matchup"].str.split().str[-1]
        frame["season"] = season
        frames[season] = frame
    return frames


def ledger(today: dt.date, logs: pd.DataFrame) -> pd.DataFrame:
    rng = random.Random(11)
    rows = []

    def add(day: dt.date, home: str, away: str, settled: bool):
        tip = dt.datetime.combine(day, dt.time(23, 30), tzinfo=dt.timezone.utc)
        for p in players():
            if p["team"] not in (home, away):
                continue
            line = round(p["base"] - 0.5 * rng.choice([0, 1]) + 0.5 - 0.5, 1)
            line = float(int(line)) + 0.5
            for version in MODELS:
                mean = p["base"] + rng.uniform(-2, 2)
                model_p = min(0.9, max(0.1, 0.5 + (mean - line) / 14))
                fair = 0.5 + rng.uniform(-0.04, 0.04)
                edge = model_p - fair
                side = "over" if edge > 0 else "under"
                pick = abs(edge) > 0.08
                row = {
                    "recorded_at": (tip - dt.timedelta(hours=rng.randint(2, 4))).isoformat(),
                    "game_date": day.isoformat(), "event_id": f"{day}{home}",
                    "commence_time": tip.isoformat(), "home": home, "away": away,
                    "player": p["player_name"], "player_id": p["player_id"], "line": line,
                    "over_odds": -112, "under_odds": -108, "model_version": version,
                    "model_mean": round(mean, 2), "model_p_over": round(model_p, 4),
                    "fair_p_over": round(fair, 4),
                    "pick_side": side if pick else None,
                    "pick_odds": (-112 if side == "over" else -108) if pick else None,
                    "pick_ev": round(abs(edge) * 1.5, 4) if pick else None,
                    "status": "pending", "stat": "points", "book": "fanduel"}
                if settled:
                    actual = int(max(0, rng.gauss(p["base"], 7)))
                    row |= {"status": "settled", "actual": actual, "went_over": actual > line}
                    if pick:
                        won = (side == "over") == (actual > line)
                        row |= {"result": "win" if won else "loss",
                                "pnl_units": 0.893 if won and side == "over" else
                                (0.926 if won else -1.0)}
                rows.append(row)

    for back in range(1, 12):
        day = today - dt.timedelta(days=back)
        add(day, *reversed(TEAMS[back % 4]), settled=True)
        add(day, *TEAMS[(back + 1) % 4], settled=True)
    for home, away in TEAMS:
        add(today, home, away, settled=False)
    from edgefinder.tracking.nba_paper import COLUMNS

    return pd.DataFrame(rows).reindex(columns=COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="a copy of the repo")
    parser.add_argument("--today", default=dt.date.today().isoformat())
    args = parser.parse_args()
    today = dt.date.fromisoformat(args.today)
    data = Path(args.root) / "data"
    (data / "nba").mkdir(parents=True, exist_ok=True)
    logs = game_logs(today)
    for season, frame in logs.items():
        frame.to_csv(data / "nba" / f"games_{season}.csv", index=False)
    ledger(today, pd.concat(logs.values())).to_csv(data / "nba_paper_log.csv", index=False)
    print(f"wrote demo data under {data}")


if __name__ == "__main__":
    main()
