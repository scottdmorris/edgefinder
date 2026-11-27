"""Simulate one game thousands of times from the players' projections.

Each run draws every player's points, rebounds, assists and threes from the same negative-binomial
spread the models price props with, around his projection, so a prop's chance here is the model's.
Team scores need one more step: teammates share one ball, so when one scores more the others
score less, and adding up independent draws swings a team's total about twice as much as real
games do. Each run therefore draws the team's score with a real game's spread (TEAM_SD, partly
shared between the teams through pace) around the sum of its projections, and the box score
splits it among the players in proportion to their draws. The players without lines tonight are
one "rest of the team" share: the team's usual scoring minus what the listed players usually score.

It is a box-score simulation, not possession by possession: it says how the projections add up
(win chance, a typical score, how often each prop clears its line), nothing the projections don't
already hold. Display only; nothing here is a pick or enters the record.
"""

from dataclasses import dataclass, field

import numpy as np

from ..models import nba_stat_model

SIMULATIONS = 5000
PACE_SD = 0.06          # the shared game-to-game swing in scoring, as a share of the projection
REST_SD = 9.0           # how much the unlisted players' combined points vary, in points
TEAM_SD = 11.5          # a team's points vary about this much game to game (2025-26 NBA)
MARGIN_BIN = 3          # points per bar in the margin chart
MARGIN_LIMIT = 30       # margins beyond this are folded into the end bars
STAT_KEYS = tuple(nba_stat_model.STATS)


@dataclass(frozen=True)
class Player:
    player_id: int
    name: str
    team: str
    means: dict[str, float]                   # stat key -> projection
    lines: dict[str, list[float]] = field(default_factory=dict)   # stat key -> lines to price


def team_target(players: list[Player], team: str, rest: float) -> float:
    return rest + sum(p.means.get("points", 0.0) for p in players if p.team == team)


def _draw(rng: np.random.Generator, means: np.ndarray, dispersion: float) -> np.ndarray:
    """Negative-binomial counts around each mean (variance = mean + mean^2 / dispersion)."""
    safe = np.maximum(means, 1e-6)
    return rng.negative_binomial(dispersion, dispersion / (dispersion + safe))


def simulate(players: list[Player], away: str, home: str, rest: dict[str, float],
             runs: int = SIMULATIONS, seed: int = 0) -> dict:
    """Run the game `runs` times. `rest` is each team's expected points from players not listed."""
    rng = np.random.default_rng(seed)
    pace = rng.lognormal(0.0, PACE_SD, runs)
    draws: dict[tuple[int, str], np.ndarray] = {}
    for player in players:
        for stat in STAT_KEYS:
            mean = player.means.get(stat)
            if mean is None:
                continue
            draws[(player.player_id, stat)] = _draw(rng, mean * pace, nba_stat_model.STATS[stat].dispersion)
    scores, shares = {}, {}
    for team in (away, home):
        listed = [draws[(p.player_id, "points")] for p in players
                  if p.team == team and (p.player_id, "points") in draws]
        others = np.maximum(rng.normal(rest.get(team, 0.0) * pace, REST_SD), 0.0)
        raw = (np.sum(listed, axis=0) if listed else 0.0) + others
        expected = team_target(players, team, rest.get(team, 0.0))
        own_sd = np.sqrt(max(TEAM_SD ** 2 - (expected * PACE_SD) ** 2, 1.0))
        scores[team] = np.maximum(expected * pace + rng.normal(0.0, own_sd, runs), 40.0)
        shares[team] = scores[team] / np.maximum(raw, 1.0)    # splits the score in draw proportion
    margin = scores[home] - scores[away]
    ties = np.isclose(margin, 0)
    home_wins = (margin > 0) | (ties & (rng.random(runs) < 0.5))     # overtime is a coin flip
    total = scores[home] + scores[away]
    return {
        "runs": runs,
        "teams": {away: _team(scores[away], ~home_wins), home: _team(scores[home], home_wins)},
        "total": _spread(total),
        "margin": _spread(margin),
        "margin_chart": _margin_chart(margin),
        "players": [_player(p, draws) for p in players],
        "typical": _typical(players, draws, scores, shares, away, home, margin, total),
    }


def _team(score: np.ndarray, wins: np.ndarray) -> dict:
    return {"win_pct": round(100 * float(wins.mean()), 1), "median": round(float(np.median(score))),
            "average": round(float(score.mean()), 1)}


def _spread(values: np.ndarray) -> dict:
    low, middle, high = np.percentile(values, [10, 50, 90])
    return {"low": round(float(low)), "median": round(float(middle)), "high": round(float(high))}


def _margin_chart(margin: np.ndarray) -> list[dict]:
    """Share of runs in each margin band, home side positive: [{from, to, pct}]."""
    clipped = np.clip(margin, -MARGIN_LIMIT, MARGIN_LIMIT - 1e-9)
    edges = np.arange(-MARGIN_LIMIT, MARGIN_LIMIT + MARGIN_BIN, MARGIN_BIN)
    counts, _ = np.histogram(clipped, bins=edges)
    return [{"from": int(a), "to": int(b), "pct": round(100 * c / len(margin), 1)}
            for a, b, c in zip(edges[:-1], edges[1:], counts)]


def _player(player: Player, draws: dict) -> dict:
    stats = {}
    for stat in STAT_KEYS:
        values = draws.get((player.player_id, stat))
        if values is None:
            continue
        stats[stat] = {
            "average": round(float(values.mean()), 1),
            "low": int(np.percentile(values, 10)), "high": int(np.percentile(values, 90)),
            # how often the run clears each line tonight: over 24.5 and "25+" are the same bet
            "lines": [{"line": line, "over_pct": round(100 * float((values > line).mean()), 1)}
                      for line in sorted(set(player.lines.get(stat, [])))],
        }
    return {"player_id": player.player_id, "player": player.name, "team": player.team, "stats": stats}


def _typical(players, draws, scores, shares, away, home, margin, total) -> dict:
    """The single run closest to the middle of everything: the median margin and total."""
    distance = (np.abs(margin - np.median(margin)) / (margin.std() or 1)
                + np.abs(total - np.median(total)) / (total.std() or 1))
    run = int(np.argmin(distance))
    def line(p: Player) -> dict:
        row = {stat: int(draws[(p.player_id, stat)][run]) for stat in STAT_KEYS
               if (p.player_id, stat) in draws}
        if "points" in row:                 # his share of the team's score in this run
            row["points"] = int(round(row["points"] * shares[p.team][run]))
        return {"player_id": p.player_id, "player": p.name, "team": p.team, **row}
    box = sorted((line(p) for p in players), key=lambda row: -row.get("points", 0))
    final = {team: int(round(scores[team][run])) for team in (away, home)}
    rest = {team: final[team] - sum(r.get("points", 0) for r in box if r["team"] == team)
            for team in (away, home)}
    return {"score": final, "rest": rest, "box": box}
