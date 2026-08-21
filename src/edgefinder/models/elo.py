"""Generic Elo rating engine, usable for MLB and NBA.

MLB defaults: small K because a 162-game season has huge game-to-game
noise; ~24 Elo points of home advantage (~54% home win rate).
NBA uses a larger K and home advantage (see nba module).
"""

from dataclasses import dataclass, field

INITIAL_RATING = 1500.0
MLB_K = 4.0
MLB_HOME_ADVANTAGE = 24.0
NBA_K = 20.0
NBA_HOME_ADVANTAGE = 70.0


@dataclass
class GameResult:
    home: str
    away: str
    home_score: int
    away_score: int


@dataclass
class EloModel:
    k: float = MLB_K
    home_advantage: float = MLB_HOME_ADVANTAGE
    ratings: dict[str, float] = field(default_factory=dict)

    def rating(self, team: str) -> float:
        return self.ratings.get(team, INITIAL_RATING)

    def expected_home_win_prob(self, home: str, away: str) -> float:
        diff = self.rating(home) + self.home_advantage - self.rating(away)
        return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))

    def update(self, game: GameResult) -> None:
        expected = self.expected_home_win_prob(game.home, game.away)
        actual = 1.0 if game.home_score > game.away_score else 0.0
        delta = self.k * (actual - expected)
        self.ratings = {
            **self.ratings,
            game.home: self.rating(game.home) + delta,
            game.away: self.rating(game.away) - delta,
        }

    def train(self, games: list[GameResult]) -> None:
        for game in games:
            self.update(game)
