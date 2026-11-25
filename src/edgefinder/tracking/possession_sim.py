"""A game played possession by possession, so it can be watched and not only summarised.

Every possession the offence's five on the floor decide what happens, in proportion to how they
play this season (last RECENT_GAMES games): who uses it (shots, free-throw trips, turnovers per
minute), whether it is a three, whether it goes in, who rebounds a miss, who assists a make, who
steals or blocks. Lineups change every few minutes in proportion to each player's minutes, with
the starters opening each half and closing the game. Each team's shooting is then tuned so its
average score matches the model's projections, so the games add up to what the model expects.

What it can't know: real positions on the floor (shot spots are drawn from typical zones for the
shot type), plays, matchups or injuries during the game. The box-score columns it lacks (threes
attempted, shots made) are estimated from league rates. Display only; never a pick.
"""

import math
import random
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

RECENT_GAMES = 15
PERIOD_SECONDS = 720
OVERTIME_SECONDS = 300
STINT_SECONDS = 240          # lineups change this often
LEAGUE_THREE_PCT = 0.36      # threes attempted are estimated from threes made at this rate
FT_PCT = 0.78
FT_TRIP_SHOTS = 2
ASSIST_SHARE = 0.60          # share of made shots that are assisted
OFFENSIVE_REBOUND = 0.25
STEAL_SHARE = 0.5            # share of turnovers that are steals
BLOCK_SHARE = 0.07           # share of missed twos that are blocked
DEFAULT_PACE = 99.0          # possessions per team per 48 minutes
TEAM_MINUTES = 240.0
CALIBRATION_RUNS = 200


@dataclass(frozen=True)
class Profile:
    player_id: int
    name: str
    team: str
    minutes: float
    usage: float             # possessions he ends per minute (shots, free-throw trips, turnovers)
    three_share: float       # of his shots, how many are threes
    two_pct: float
    three_pct: float
    trip_share: float        # of his possessions, how many are free-throw trips
    tov_share: float
    rebounds: float          # per minute
    assists: float
    steals: float
    blocks: float
    starter: bool = False


def profile(name: str, player_id: int, team: str, logs: pd.DataFrame, minutes: float | None = None,
            points: float | None = None) -> Profile | None:
    """A player's rates from his recent games; `points` (his projection) scales how much he
    shoots so the model's view carries into the game."""
    recent = logs.sort_values("game_date").tail(RECENT_GAMES)
    played = float(recent["minutes"].sum())
    if played < 30:
        return None
    total = recent[["fga", "fta", "fg3m", "pts", "reb", "ast", "tov", "stl", "blk"]].sum()
    threes = min(total["fg3m"] / LEAGUE_THREE_PCT, total["fga"] * 0.9)
    twos = max(total["fga"] - threes, 1.0)
    made_twos = max(total["pts"] - 3 * total["fg3m"] - FT_PCT * total["fta"], 0.0) / 2
    trips = total["fta"] / FT_TRIP_SHOTS
    ends = total["fga"] + trips + total["tov"]
    if ends <= 0:
        return None
    per_game_minutes = minutes if minutes else played / len(recent)
    usage = ends / played
    if points is not None and total["pts"] > 0:
        usage *= float(np.clip(points / (total["pts"] / len(recent)) * (played / len(recent)) / per_game_minutes,
                               0.7, 1.4))
    return Profile(
        player_id=player_id, name=name, team=team, minutes=per_game_minutes, usage=usage,
        three_share=float(threes / max(total["fga"], 1.0)),
        two_pct=float(np.clip(made_twos / twos, 0.30, 0.75)), three_pct=LEAGUE_THREE_PCT,
        trip_share=float(trips / ends), tov_share=float(total["tov"] / ends),
        rebounds=float(total["reb"] / played), assists=float(total["ast"] / played),
        steals=float(total["stl"] / played), blocks=float(total["blk"] / played))


def bench(team: str, minutes: float, points: float, count: int, first_id: int) -> list[Profile]:
    """Stand-ins for the players without lines, so a team always has five on the floor. Their ids
    are negative (first_id, first_id - 1, ...) so they never meet a real player's."""
    each = minutes / count
    usage = max(points, 1.0) / max(minutes, 1.0) / 1.05
    return [Profile(player_id=first_id - i, name=f"{team} bench",
                    team=team, minutes=each, usage=usage, three_share=0.38, two_pct=0.52,
                    three_pct=LEAGUE_THREE_PCT, trip_share=0.10, tov_share=0.13, rebounds=0.17,
                    assists=0.10, steals=0.03, blocks=0.02) for i in range(count)]


# ---- one game ---------------------------------------------------------------------------------

def _pick(rng: random.Random, people: list[Profile], weight) -> Profile:
    weights = [max(weight(p), 1e-6) for p in people]
    return rng.choices(people, weights)[0]


def _lineup(rng: random.Random, roster: list[Profile], starters: bool) -> list[Profile]:
    if starters or len(roster) <= 5:
        return [p for p in roster if p.starter][:5] or roster[:5]
    pool, chosen = list(roster), []
    while len(chosen) < 5 and pool:
        player = _pick(rng, pool, lambda p: p.minutes)
        chosen.append(player)
        pool.remove(player)
    return chosen


def _spot(rng: random.Random, three: bool, attacking_right: bool) -> tuple[float, float]:
    """A shot spot in court percent (x along the length, y across), drawn from typical zones."""
    if three:
        corner = rng.random() < 0.3
        if corner:
            depth, side = rng.uniform(1, 13), rng.choice((-1, 1)) * rng.uniform(22.2, 23.5)
        else:
            angle = rng.uniform(-1.15, 1.15)
            reach = rng.uniform(24, 27)
            depth, side = 5.25 + reach * math.cos(angle), reach * math.sin(angle)
    else:
        zone = rng.random()
        reach = rng.uniform(0, 4) if zone < 0.45 else rng.uniform(4, 14) if zone < 0.75 else rng.uniform(14, 21)
        angle = rng.uniform(-1.4, 1.4)
        depth, side = 5.25 + reach * math.cos(angle), reach * math.sin(angle)
    x = max(depth, 0.5) / 94 * 100
    y = (25 + side) / 50 * 100
    return (100 - x, 100 - y) if attacking_right else (x, y)


def play_game(rosters: dict[str, list[Profile]], away: str, home: str, pace: float,
              rng: random.Random, record: bool = False, shooting: dict[str, float] | None = None) -> dict:
    """One game. With `record`, every event is kept so it can be replayed."""
    shooting = shooting or {}
    seconds_per = 2880 / (2 * pace)                 # average possession length for this pace
    score = {away: 0, home: 0}
    box = {p.player_id: {"points": 0, "rebounds": 0, "assists": 0, "threes": 0, "fga": 0, "fgm": 0,
                         "steals": 0, "blocks": 0, "turnovers": 0}
           for team in (away, home) for p in rosters[team]}
    events: list[dict] = []
    offense = rng.choice((away, home))
    period, elapsed = 1, 0.0
    lineups = {t: _lineup(rng, rosters[t], True) for t in (away, home)}
    next_change = STINT_SECONDS

    def log(kind: str, team: str, text: str, **extra) -> None:
        if record:
            left = _period_length(period) - (elapsed - _period_start(period))
            events.append({"t": round(elapsed, 1), "period": period, "clock": _clock(left), "kind": kind,
                           "team": team, "text": text, "away": score[away], "home": score[home],
                           "on": {t: [p.player_id for p in lineups[t]] for t in (away, home)}, **extra})

    def attacking_right(team: str) -> bool:      # home attacks right in the first half, as on TV
        first_half = period <= 2
        return (team == home) == first_half

    log("start", "", "Tip-off")
    while True:
        end = _period_start(period) + _period_length(period)
        if elapsed >= end:
            log("period", "", f"End of {_period_name(period)}")
            if period >= 4 and score[away] != score[home]:
                break
            period += 1
            elapsed = _period_start(period)
            closing = period >= 4
            lineups = {t: _lineup(rng, rosters[t], period in (1, 3) or closing) for t in (away, home)}
            next_change = elapsed + STINT_SECONDS
            continue
        if elapsed >= next_change:
            late = period >= 4 and end - elapsed < STINT_SECONDS
            lineups = {t: _lineup(rng, rosters[t], late) for t in (away, home)}
            next_change = elapsed + STINT_SECONDS
        defense = home if offense == away else away
        on_offense, on_defense = lineups[offense], lineups[defense]
        elapsed = min(elapsed + max(rng.gauss(seconds_per, 5.0), 4.0), end)
        owner = _pick(rng, on_offense, lambda p: p.usage)
        roll = rng.random()
        if roll < owner.tov_share:
            box[owner.player_id]["turnovers"] += 1
            if rng.random() < STEAL_SHARE:
                thief = _pick(rng, on_defense, lambda p: p.steals)
                box[thief.player_id]["steals"] += 1
                log("steal", defense, f"{thief.name} steal", player=thief.player_id, against=owner.player_id)
            else:
                log("turnover", offense, f"{owner.name} turnover", player=owner.player_id)
            offense = defense
            continue
        if roll < owner.tov_share + owner.trip_share:
            made = sum(rng.random() < FT_PCT for _ in range(FT_TRIP_SHOTS))
            score[offense] += made
            box[owner.player_id]["points"] += made
            x, y = _spot(rng, False, attacking_right(offense))
            log("free_throws", offense, f"{owner.name} {made} of {FT_TRIP_SHOTS} free throws",
                player=owner.player_id, points=made, x=(94 - 19) / 94 * 100 if attacking_right(offense) else 19 / 94 * 100, y=50)
            offense = defense
            continue
        # a shot, and any offensive rebounds after it
        shooter = owner
        while True:
            three = rng.random() < shooter.three_share
            chance = (shooter.three_pct if three else shooter.two_pct) * shooting.get(offense, 1.0)
            made = rng.random() < chance
            x, y = _spot(rng, three, attacking_right(offense))
            stats = box[shooter.player_id]
            stats["fga"] += 1
            if made:
                points = 3 if three else 2
                score[offense] += points
                stats["points"] += points
                stats["fgm"] += 1
                stats["threes"] += int(three)
                helper = None
                if rng.random() < ASSIST_SHARE and len(on_offense) > 1:
                    helper = _pick(rng, [p for p in on_offense if p is not shooter], lambda p: p.assists)
                    box[helper.player_id]["assists"] += 1
                log("make", offense, f"{shooter.name} {_shot_name(three, x, y, attacking_right(offense))}"
                    + (f", {helper.name} assist" if helper else ""),
                    player=shooter.player_id, assist=helper.player_id if helper else None,
                    points=points, x=round(x, 1), y=round(y, 1), three=three)
                offense = defense
                break
            blocked = not three and rng.random() < BLOCK_SHARE
            if blocked:
                blocker = _pick(rng, on_defense, lambda p: p.blocks)
                box[blocker.player_id]["blocks"] += 1
            log("miss", offense, f"{shooter.name} misses {_shot_name(three, x, y, attacking_right(offense))}"
                + (f", blocked by {blocker.name}" if blocked else ""),
                player=shooter.player_id, x=round(x, 1), y=round(y, 1), three=three)
            if rng.random() < OFFENSIVE_REBOUND:
                grabber = _pick(rng, on_offense, lambda p: p.rebounds)
                box[grabber.player_id]["rebounds"] += 1
                log("rebound", offense, f"{grabber.name} offensive rebound", player=grabber.player_id)
                elapsed = min(elapsed + rng.uniform(2, 8), end)
                shooter = _pick(rng, on_offense, lambda p: p.usage)
                if elapsed >= end:
                    break
                continue
            grabber = _pick(rng, on_defense, lambda p: p.rebounds)
            box[grabber.player_id]["rebounds"] += 1
            log("rebound", defense, f"{grabber.name} rebound", player=grabber.player_id)
            offense = defense
            break
    log("final", "", f"Final: {away} {score[away]}, {home} {score[home]}")
    return {"score": dict(score), "box": box, "events": events, "periods": period}


def _period_length(period: int) -> int:
    return PERIOD_SECONDS if period <= 4 else OVERTIME_SECONDS


def _period_start(period: int) -> int:
    return PERIOD_SECONDS * min(period - 1, 4) + OVERTIME_SECONDS * max(period - 5, 0)


def _period_name(period: int) -> str:
    return f"Q{period}" if period <= 4 else f"OT{period - 4}"


def _clock(seconds_left: float) -> str:
    seconds_left = max(seconds_left, 0.0)
    return f"{int(seconds_left // 60)}:{int(seconds_left % 60):02d}"


def _shot_name(three: bool, x: float, y: float, right: bool) -> str:
    depth = (100 - x if right else x) / 100 * 94 - 5.25
    side = (y - 50) / 100 * 50
    distance = math.hypot(depth, side)
    if three:
        return f"{max(round(distance), 22)}-foot three"
    if distance < 4:
        return "layup" if distance > 1.5 else "dunk"
    return f"{round(distance)}-foot jumper"


# ---- many games -------------------------------------------------------------------------------

def tune(rosters: dict[str, list[Profile]], away: str, home: str, pace: float,
         targets: dict[str, float], seed: int) -> dict[str, float]:
    """How much to lift or lower each team's shooting so its average score meets its target."""
    shooting = {away: 1.0, home: 1.0}
    for _ in range(2):
        rng = random.Random(seed)
        totals = {away: 0.0, home: 0.0}
        for _ in range(CALIBRATION_RUNS):
            score = play_game(rosters, away, home, pace, rng, shooting=shooting)["score"]
            for team in totals:
                totals[team] += score[team]
        for team in totals:
            average = totals[team] / CALIBRATION_RUNS
            if average > 0 and targets.get(team):
                shooting[team] = float(np.clip(shooting[team] * (targets[team] / average) ** 1.3, 0.75, 1.3))
    return shooting


def win_chances(events: list[dict], away: str, home: str, margin_mean: float, margin_sd: float) -> list[dict]:
    """Each event with the home side's chance to win from that point: the score now plus the
    rest of the game's expected margin, its spread shrinking as time runs out."""
    out = []
    for event in events:
        left = max(2880 - event["t"], 0) / 2880
        lead = event["home"] - event["away"]
        if left <= 0:
            chance = 1.0 if lead > 0 else 0.0 if lead < 0 else 0.5
        else:
            z = (lead + margin_mean * left) / (margin_sd * math.sqrt(left))
            chance = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        out.append({**event, "home_win": round(100 * chance, 1)})
    return out


def simulate(rosters: dict[str, list[Profile]], away: str, home: str, pace: float,
             targets: dict[str, float], runs: int, seed: int) -> dict:
    """`runs` games: the summary of all of them and the most typical one, event by event."""
    shooting = tune(rosters, away, home, pace, targets, seed)
    rng = random.Random(seed + 1)
    games = [play_game(rosters, away, home, pace, rng, shooting=shooting) for _ in range(runs)]
    scores = {t: np.array([g["score"][t] for g in games], dtype=float) for t in (away, home)}
    margin = scores[home] - scores[away]
    total = scores[home] + scores[away]
    distance = (np.abs(margin - np.median(margin)) / (margin.std() or 1)
                + np.abs(total - np.median(total)) / (total.std() or 1))
    typical = int(np.argmin(distance))
    # replay the typical game with its events recorded: same draws, same result
    replay_rng = random.Random(seed + 1)
    for _ in range(typical):
        play_game(rosters, away, home, pace, replay_rng, shooting=shooting)
    watched = play_game(rosters, away, home, pace, replay_rng, record=True, shooting=shooting)
    events = win_chances(watched["events"], away, home, float(margin.mean()), float(margin.std() or 12))
    return {"scores": scores, "margin": margin, "total": total, "games": games, "watched": {**watched, "events": events},
            "shooting": shooting}


def starters(roster: list[Profile]) -> list[Profile]:
    """The five who play the most minutes start."""
    first = {p.player_id for p in sorted(roster, key=lambda p: -p.minutes)[:5]}
    return [replace(p, starter=p.player_id in first) for p in roster]
