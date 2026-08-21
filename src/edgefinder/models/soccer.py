"""Soccer match model: Poisson attack/defense strengths.

Each team gets a multiplicative attack and defense rating relative to
league average; expected goals for a match combine both teams' ratings
with the league's home/away scoring rates. Win/draw/win and totals
probabilities come from the full score matrix.

This is the standard baseline (Maher 1982). The Dixon-Coles low-score
correction is a known refinement on the roadmap.
"""

from dataclasses import dataclass

from ..betting import poisson

MAX_GOALS = 10  # score matrix upper bound per team
MIN_MATCHES = 5


@dataclass(frozen=True)
class Match:
    home: str
    away: str
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class LeagueModel:
    attack: dict[str, float]      # >1 scores more than league average
    defense: dict[str, float]     # <1 concedes less than league average
    avg_home_goals: float
    avg_away_goals: float

    def teams(self) -> set[str]:
        return set(self.attack)


def fit_league(matches: list[Match]) -> LeagueModel:
    if len(matches) < MIN_MATCHES:
        raise ValueError("Not enough matches to fit a league model")
    scored: dict[str, list[int]] = {}
    conceded: dict[str, list[int]] = {}
    for m in matches:
        scored.setdefault(m.home, []).append(m.home_goals)
        conceded.setdefault(m.home, []).append(m.away_goals)
        scored.setdefault(m.away, []).append(m.away_goals)
        conceded.setdefault(m.away, []).append(m.home_goals)
    total_goals = sum(m.home_goals + m.away_goals for m in matches)
    avg_per_team_game = total_goals / (2 * len(matches))
    attack = {
        team: (sum(goals) / len(goals)) / avg_per_team_game
        for team, goals in scored.items()
    }
    defense = {
        team: (sum(goals) / len(goals)) / avg_per_team_game
        for team, goals in conceded.items()
    }
    return LeagueModel(
        attack=attack,
        defense=defense,
        avg_home_goals=sum(m.home_goals for m in matches) / len(matches),
        avg_away_goals=sum(m.away_goals for m in matches) / len(matches),
    )


def expected_goals(model: LeagueModel, home: str, away: str) -> tuple[float, float]:
    home_rate = (model.avg_home_goals
                 * model.attack.get(home, 1.0) * model.defense.get(away, 1.0))
    away_rate = (model.avg_away_goals
                 * model.attack.get(away, 1.0) * model.defense.get(home, 1.0))
    return max(0.1, home_rate), max(0.1, away_rate)


def score_matrix(home_rate: float, away_rate: float) -> list[list[float]]:
    return [
        [poisson.pmf(h, home_rate) * poisson.pmf(a, away_rate)
         for a in range(MAX_GOALS + 1)]
        for h in range(MAX_GOALS + 1)
    ]


def match_probs(home_rate: float, away_rate: float) -> dict[str, float]:
    """P(home win), P(draw), P(away win)."""
    matrix = score_matrix(home_rate, away_rate)
    home = sum(matrix[h][a] for h in range(MAX_GOALS + 1)
               for a in range(MAX_GOALS + 1) if h > a)
    draw = sum(matrix[g][g] for g in range(MAX_GOALS + 1))
    away = sum(matrix[h][a] for h in range(MAX_GOALS + 1)
               for a in range(MAX_GOALS + 1) if h < a)
    total = home + draw + away
    return {"home": home / total, "draw": draw / total, "away": away / total}


def total_goals_probs(home_rate: float, away_rate: float, line: float) -> dict[str, float]:
    """P(over)/P(under) for a goals line (half-point lines only in
    practice for soccer)."""
    return poisson.no_push_probs(line, home_rate + away_rate)
