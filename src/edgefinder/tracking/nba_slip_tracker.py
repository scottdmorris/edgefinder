"""Is each bet on a slip hit, still alive, or dead? Decided from live box scores.

The rules, in plain terms. A bet needs `target` points, the smallest whole
number that clears the line (24.5 needs 25; "25+" needs 25).

- Over / X+: hit the moment the player reaches the target, and it stays hit.
  Missed once the game is final without him getting there. Otherwise alive.
- Under: missed the moment the player reaches the target, and it stays
  missed. Hit once the game is final with him still below it. Otherwise alive.
- A player who never got in the game voids the bet once it is final.

A slip is missed as soon as any bet is missed, hit when every bet that
counts is hit, and otherwise still alive.
"""

import math
from dataclasses import dataclass

import pandas as pd

from ..data.nba_live import FINAL, LIVE, Exit, LiveGame, PlayerLine

HIT, ALIVE, MISSED, NOT_STARTED, VOID = "Hit", "Alive", "Missed", "Not started", "Didn't play"

# what each stat counts in the live box score, and what to call it
COUNTED = {"points": ("points", "points"), "rebounds": ("rebounds", "rebounds"),
           "assists": ("assists", "assists"), "threes": ("threes", "3-pointers")}


@dataclass(frozen=True)
class Progress:
    status: str
    have: int | None         # points so far; None before tip-off
    target: int
    detail: str


def target_points(line: float) -> int:
    """Fewest counted that beat a half-point line: 24.5 -> 25."""
    return math.floor(line) + 1


def leg_progress(is_over: bool, line: float, game_status: int,
                 player: PlayerLine | None, stat: str = "points") -> Progress:
    target = target_points(line)
    column, unit = COUNTED.get(stat, COUNTED["points"])
    if game_status < LIVE:
        return Progress(NOT_STARTED, None, target, "game hasn't started")
    if player is None or not player.played:
        if game_status == FINAL:
            return Progress(VOID, None, target, "didn't play, so the bet is void")
        return Progress(ALIVE, 0, target, "hasn't entered the game yet")

    have, final = int(getattr(player, column)), game_status == FINAL
    if is_over:
        if have >= target:
            return Progress(HIT, have, target, f"{have} {unit}, needed {target}")
        if final:
            return Progress(MISSED, have, target, f"finished with {have}, needed {target}")
        return Progress(ALIVE, have, target, f"{have} {unit} so far, needs {target - have} more")
    if have >= target:
        return Progress(MISSED, have, target, f"already at {have}, over the line")
    if final:
        return Progress(HIT, have, target, f"finished with {have}, under the line")
    return Progress(ALIVE, have, target,
                    f"{have} {unit} so far, can add {target - 1 - have} more and still win")


FOUL_LIMIT = 6
TECHNICAL_LIMIT = 2
PERIOD_MINUTES, OVERTIME_MINUTES, REGULATION_PERIODS = 12.0, 5.0, 4
LONG_SIT_STARTER = 10.0      # game minutes on the bench before a starter's absence is worth a warning
LONG_SIT_BENCH = 16.0


def game_minutes(period: int, seconds_left: float) -> float:
    """Game time played when the clock shows `seconds_left` in `period`."""
    if period <= 0:
        return 0.0
    before = (min(period - 1, REGULATION_PERIODS) * PERIOD_MINUTES
              + max(period - 1 - REGULATION_PERIODS, 0) * OVERTIME_MINUTES)
    length = PERIOD_MINUTES if period <= REGULATION_PERIODS else OVERTIME_MINUTES
    return before + length - min(seconds_left / 60.0, length)


def _clock_seconds(clock: str) -> float:
    minutes, _, seconds = (clock or "0:00").partition(":")
    try:
        return int(minutes) * 60.0 + float(seconds or 0)
    except ValueError:
        return 0.0


def exit_alert(player: PlayerLine | None, exit: Exit | None, game: LiveGame) -> str:
    """Why a player who has played may be done for the night, or '' when nothing says so.

    Certain when the box score says it (fouled out, ejected, listed out). A long stretch on the
    bench is only a warning: NBA's feed does not announce a mid-game injury, so the absence is
    the signal."""
    if player is None or not player.played or game.status != LIVE:
        return ""
    if (exit and exit.ejected) or player.technicals >= TECHNICAL_LIMIT:
        return "Ejected"
    if player.fouls >= FOUL_LIMIT:
        return "Fouled out"
    if player.on_court:
        return ""
    if player.not_playing:
        return f"Listed out: {player.not_playing}"
    if exit is None or not exit.out_period:
        return ""
    sat = (game_minutes(game.period, _clock_seconds(game.clock))
           - game_minutes(exit.out_period, exit.out_seconds_left))
    if sat >= (LONG_SIT_STARTER if player.starter else LONG_SIT_BENCH):
        return f"Off the floor for the last {sat:.0f} minutes of game time. May be hurt or benched"
    return ""


def slip_status(statuses: list[str]) -> str:
    """Overall status of a slip from its bets' statuses."""
    if MISSED in statuses:
        return MISSED
    counting = [s for s in statuses if s != VOID]
    if not counting:
        return VOID
    if all(s == HIT for s in counting):
        return HIT
    if all(s == NOT_STARTED for s in counting):
        return NOT_STARTED
    return ALIVE


def find_game(games: list[LiveGame], away: str | None, home: str | None) -> LiveGame | None:
    return next((g for g in games if g.away == away and g.home == home), None)


def track_slip(chosen: pd.DataFrame, games: list[LiveGame], fetch_box) -> pd.DataFrame:
    """One row per bet with its progress. `fetch_box(game_id)` returns the
    box score; it is called at most once per game, and only for games that
    have started."""
    boxes: dict[str, dict[int, PlayerLine]] = {}
    rows = []
    for bet in chosen.itertuples():
        game = find_game(games, bet.away_abbr, bet.home_abbr)
        if game is None:
            rows.append(_row(bet, None, Progress(NOT_STARTED, None, target_points(bet.line),
                                                 "no live game found for this matchup")))
            continue
        player = None
        if game.status >= LIVE:
            if game.game_id not in boxes:
                boxes[game.game_id] = fetch_box(game.game_id)
            player = boxes[game.game_id].get(int(bet.player_id))
        rows.append(_row(bet, game, leg_progress(bool(bet.is_over), bet.line, game.status, player,
                                                  getattr(bet, "stat_key", "points"))))
    return pd.DataFrame(rows)


def _row(bet, game: LiveGame | None, progress: Progress) -> dict:
    return {
        "Leg": bet.Leg, "player_id": int(bet.player_id), "Status": progress.status,
        "Have": progress.have, "Target": progress.target, "Detail": progress.detail,
        "Game": game_text(game),
        "Progress": 0.0 if progress.have is None else min(1.0, progress.have / progress.target),
        "Is over": bool(bet.is_over),
    }


def game_text(game: LiveGame | None) -> str:
    if game is None:
        return "no live game"
    score = f"{game.away} {game.away_score} - {game.home} {game.home_score}"
    if game.status == LIVE:
        clock = f" {game.clock}" if game.clock else ""
        return f"{score}  ·  {game.status_text}{clock}"
    return f"{score}  ·  {game.status_text}" if game.status == FINAL else \
        f"{game.away} @ {game.home}  ·  {game.status_text}"
