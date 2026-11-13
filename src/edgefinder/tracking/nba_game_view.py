"""What the game center shows, worked out from a game's live numbers.

Pure shaping with no web framework in it: the court drawing, shot totals, team
comparison rows, leaders and the quarter-by-quarter table.
"""

import math
from dataclasses import replace

import numpy as np
import pandas as pd

from ..data.nba_live import Play, PlayerLine, Shot

# real court, in feet
COURT_LENGTH, COURT_WIDTH = 94.0, 50.0
HOOP_X, HOOP_Y = 5.25, 25.0
THREE_RADIUS, THREE_CORNER_Y = 23.75, 3.0
PAINT_LENGTH, PAINT_HALF_WIDTH = 19.0, 8.0
CIRCLE_RADIUS = 6.0


def _arc(cx: float, cy: float, radius: float, start: float, stop: float,
         steps: int = 48) -> list[tuple[float, float]]:
    angles = np.linspace(start, stop, steps)
    return [(cx + radius * math.cos(a), cy + radius * math.sin(a)) for a in angles]


def _half_court() -> dict[str, list[tuple[float, float]]]:
    """The markings around the basket on the left end, in feet."""
    corner_x = HOOP_X + math.sqrt(THREE_RADIUS ** 2 - (HOOP_Y - THREE_CORNER_Y) ** 2)
    arc_ys = np.linspace(THREE_CORNER_Y, COURT_WIDTH - THREE_CORNER_Y, 60)
    arc = [(HOOP_X + math.sqrt(THREE_RADIUS ** 2 - (y - HOOP_Y) ** 2), y) for y in arc_ys]
    return {
        "paint": [(0, HOOP_Y - PAINT_HALF_WIDTH), (PAINT_LENGTH, HOOP_Y - PAINT_HALF_WIDTH),
                  (PAINT_LENGTH, HOOP_Y + PAINT_HALF_WIDTH), (0, HOOP_Y + PAINT_HALF_WIDTH)],
        "free throw circle": _arc(PAINT_LENGTH, HOOP_Y, CIRCLE_RADIUS, 0, 2 * math.pi),
        "three point line": [(0, THREE_CORNER_Y), (corner_x, THREE_CORNER_Y), *arc,
                             (corner_x, COURT_WIDTH - THREE_CORNER_Y),
                             (0, COURT_WIDTH - THREE_CORNER_Y)],
        "restricted area": _arc(HOOP_X, HOOP_Y, 4.0, -math.pi / 2, math.pi / 2),
        "backboard": [(4.0, HOOP_Y - 3), (4.0, HOOP_Y + 3)],
        "hoop": _arc(HOOP_X, HOOP_Y, 0.75, 0, 2 * math.pi),
    }


def court_lines() -> pd.DataFrame:
    """Every court marking as points (x, y) on a 0-100 scale across the full
    court, with a `line` id and an `order` to draw each in sequence. The same
    0-100 scale the shot locations use, so they sit on top of it exactly."""
    lines = {
        "boundary": [(0, 0), (COURT_LENGTH, 0), (COURT_LENGTH, COURT_WIDTH),
                     (0, COURT_WIDTH), (0, 0)],
        "half court": [(COURT_LENGTH / 2, 0), (COURT_LENGTH / 2, COURT_WIDTH)],
        "center circle": _arc(COURT_LENGTH / 2, COURT_WIDTH / 2, CIRCLE_RADIUS, 0, 2 * math.pi),
    }
    for name, points in _half_court().items():
        lines[f"left {name}"] = points
        lines[f"right {name}"] = [(COURT_LENGTH - x, y) for x, y in points]
    rows = [(x / COURT_LENGTH * 100.0, y / COURT_WIDTH * 100.0, name, order)
            for name, points in lines.items() for order, (x, y) in enumerate(points)]
    return pd.DataFrame(rows, columns=["x", "y", "line", "order"])


def to_ends(shots: list[Shot], away: str, home: str) -> list[Shot]:
    """Every shot drawn at its team's own end, the way game apps show it: the away team at the
    left basket, the home team at the right. Teams switch ends at halftime, so a shot at the
    other end is turned around the center of the court (both coordinates flipped)."""
    placed = []
    for shot in shots:
        wrong_end = (shot.team == away and shot.x > 50) or (shot.team == home and shot.x < 50)
        placed.append(replace(shot, x=100 - shot.x, y=100 - shot.y) if wrong_end else shot)
    return placed


def shots_in_period(shots: list[Shot], period: int | None) -> list[Shot]:
    """One period's shots, or all of them when `period` is None."""
    return shots if period is None else [s for s in shots if s.period == period]


def shot_summary(shots: list[Shot], team: str) -> dict:
    """A team's makes, attempts and threes, as the chart header shows them."""
    mine = [s for s in shots if s.team == team]
    threes = [s for s in mine if s.is_three]
    made = sum(s.made for s in mine)
    return {
        "made": made, "attempts": len(mine),
        "pct": made / len(mine) * 100.0 if mine else 0.0,
        "threes_made": sum(s.made for s in threes), "threes_attempts": len(threes),
    }


def shot_table(shots: list[Shot]) -> pd.DataFrame:
    return pd.DataFrame({
        "x": [s.x for s in shots], "y": [s.y for s in shots],
        "Team": [s.team for s in shots], "Player": [s.player for s in shots],
        "Result": ["Made" if s.made else "Missed" for s in shots],
        "Distance (ft)": [round(s.distance, 1) for s in shots],
        "Period": [s.period for s in shots],
        "Play": [s.description for s in shots],
    })


def _split(stats: dict, made: str, attempts: str) -> tuple[float, str]:
    m, a = stats[made], stats[attempts]
    return (m / a * 100.0 if a else 0.0), f"{m / a * 100:.1f}% ({m:.0f}/{a:.0f})" if a \
        else f"0.0% ({m:.0f}/{a:.0f})"


# (label, made field, attempts field) for shooting; (label, field, higher is better) for counts
SHOOTING = (
    ("Field goals", "fieldGoalsMade", "fieldGoalsAttempted"),
    ("3-pointers", "threePointersMade", "threePointersAttempted"),
    ("Free throws", "freeThrowsMade", "freeThrowsAttempted"),
)
COUNTS = (
    ("Rebounds", "reboundsTotal", True), ("Assists", "assists", True),
    ("Steals", "steals", True), ("Blocks", "blocks", True),
    ("Turnovers", "turnovers", False), ("Points in the paint", "pointsInThePaint", True),
    ("Fast break points", "pointsFastBreak", True),
    ("Second chance points", "pointsSecondChance", True),
    ("Points off turnovers", "pointsFromTurnovers", True),
    ("Bench points", "benchPoints", True), ("Biggest lead", "biggestLead", True),
)


def comparison_rows(away: dict, home: dict) -> list[dict]:
    """Side-by-side team numbers. Each row says what to print for each team,
    how long each bar is (0 to 1 of the pair), and which side is ahead. A
    stat either team's data lacks is skipped, not shown as zero."""
    rows = []
    for label, made, attempts in SHOOTING:
        if all(k in side for side in (away, home) for k in (made, attempts)):
            a_value, a_text = _split(away, made, attempts)
            h_value, h_text = _split(home, made, attempts)
            rows.append(_row(label, a_text, h_text, a_value, h_value, True))
    for label, field, higher_is_better in COUNTS:
        if field in away and field in home:
            rows.append(_row(label, f"{away[field]:.0f}", f"{home[field]:.0f}",
                             away[field], home[field], higher_is_better))
    return rows


def _row(label: str, away_text: str, home_text: str, away_value: float, home_value: float,
         higher_is_better: bool) -> dict:
    total = away_value + home_value
    share = away_value / total if total else 0.5
    if away_value == home_value:
        ahead = ""
    else:
        away_leads = (away_value > home_value) == higher_is_better
        ahead = "away" if away_leads else "home"
    return {"label": label, "away_text": away_text, "home_text": home_text,
            "away_share": share, "ahead": ahead}


def leaders(players: dict[int, PlayerLine], team: str) -> dict[str, PlayerLine | None]:
    """The team's top scorer, rebounder and assister so far."""
    roster = [p for p in players.values() if p.team == team and p.played]
    best = lambda key: max(roster, key=key) if roster else None   # noqa: E731
    return {"Points": best(lambda p: p.points), "Rebounds": best(lambda p: p.rebounds),
            "Assists": best(lambda p: p.assists)}


def quarter_table(period_scores: dict[str, list[int]], away: str, home: str,
                  away_total: int, home_total: int) -> pd.DataFrame:
    """Points by period for both teams with a final column, like a TV score bug."""
    periods = max((len(v) for v in period_scores.values()), default=0)
    names = [f"Q{n}" if n <= 4 else f"OT{n - 4}" for n in range(1, periods + 1)]
    table = pd.DataFrame(
        {name: [period_scores.get(away, [])[i] if i < len(period_scores.get(away, [])) else 0,
                period_scores.get(home, [])[i] if i < len(period_scores.get(home, [])) else 0]
         for i, name in enumerate(names)},
        index=[away, home])
    table["Total"] = [away_total, home_total]
    return table


FOUL_TROUBLE = 4          # four fouls is where a coach starts to worry
FOULED_OUT = 6


def chip_label(away: str, home: str, away_score: int, home_score: int, state: str,
               status: str, clock: str = "") -> str:
    """A game as one tappable chip, like a sportsbook's score strip:
    'MIA 83-98 GSW · Q4 8:34' live, 'ORL 104-117 PHX · Final' finished, 'MIA @ GSW · 10:00 pm ET'
    before tip-off."""
    if state == "upcoming":
        return f"{away} @ {home} · {status}"
    if state == "final":
        return f"{away} {away_score}-{home_score} {home} · Final"
    period = status.replace(" Qtr", "").replace("1st", "Q1").replace("2nd", "Q2") \
        .replace("3rd", "Q3").replace("4th", "Q4")
    return f"{away} {away_score}-{home_score} {home} · {period} {clock}".rstrip()


def new_plays(last_seen: int | None, orders: list[int]) -> set[int]:
    """The plays that arrived since the last refresh (by their order number). The first look
    at a game marks nothing new, so the feed doesn't light up on page load."""
    if last_seen is None:
        return set()
    return {order for order in orders if order > last_seen}


def changed_status(before: dict[str, str], now: dict[str, str]) -> set[str]:
    """Slip legs whose status changed since the last refresh (alive -> hit, say). A leg seen
    for the first time has not changed."""
    return {leg for leg, status in now.items() if leg in before and before[leg] != status}


def score_deltas(previous: dict[str, tuple[int, int]],
                 current: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    """Points each team scored since the last look, for games seen both times: {game id:
    (away, home)}, only where someone scored. A game seen for the first time has no
    change, so nothing pops when the page first loads, and a score that went down
    (a correction) shows nothing rather than a negative."""
    changes = {}
    for game_id, (away, home) in current.items():
        if game_id not in previous:
            continue
        before_away, before_home = previous[game_id]
        away_gain, home_gain = max(0, away - before_away), max(0, home - before_home)
        if away_gain or home_gain:
            changes[game_id] = (away_gain, home_gain)
    return changes


def foul_trouble(players: dict[int, PlayerLine], team: str) -> list[tuple[str, int]]:
    """Players on a team with four or more fouls, most fouls first: [(name, fouls)]."""
    chosen = [(p.name, p.fouls) for p in players.values()
              if p.team == team and p.played and p.fouls >= FOUL_TROUBLE]
    return sorted(chosen, key=lambda item: (-item[1], item[0]))


def foul_line(team: str, team_stats: dict[str, dict[str, float]],
              players: dict[int, PlayerLine]) -> str:
    """One team's fouls for the score header: 'GSW fouls 12 · foul trouble: Green 5, Curry 4'.
    Empty when the feed carries neither number."""
    fouls = team_stats.get(team, {}).get("foulsPersonal")
    trouble = foul_trouble(players, team)
    parts = []
    if fouls is not None:
        parts.append(f"fouls {int(fouls)}")
    if trouble:
        names = ", ".join(f"{name.split()[-1]} {count}" for name, count in trouble)
        parts.append(f"foul trouble: {names}")
    return f"{team} " + " · ".join(parts) if parts else ""


def box_table(players: dict[int, PlayerLine], team: str, starters: bool) -> pd.DataFrame:
    """Starters or bench for one team, highest scorer first, with the shooting
    splits a box score carries. Players who haven't played are left out."""
    chosen = [p for p in players.values()
              if p.team == team and p.played and p.starter == starters]
    chosen.sort(key=lambda p: (-p.points, -p.minutes))
    return pd.DataFrame({
        "player_id": [p.player_id for p in chosen],
        "Player": [p.name + ("  🏀" if p.on_court else "") for p in chosen],
        "Min": [round(p.minutes) for p in chosen],
        "Pts": [p.points for p in chosen],
        "Reb": [p.rebounds for p in chosen], "Ast": [p.assists for p in chosen],
        "FG": [f"{p.fg_made}-{p.fg_att}" for p in chosen],
        "3PT": [f"{p.threes}-{p.three_att}" for p in chosen],
        "FT": [f"{p.ft_made}-{p.ft_att}" for p in chosen],
        "Stl": [p.steals for p in chosen], "Blk": [p.blocks for p in chosen],
        "TO": [p.turnovers for p in chosen], "PF": [p.fouls for p in chosen],
        "+/-": [f"{p.plus_minus:+.0f}" for p in chosen],
    })


# ---- the shape of the game -------------------------------------------------------------------------

RUN_MIN_POINTS = 8             # a team needs this many in the stretch for it to be called a run
RUN_MAX_SHARE = 1 / 3          # while giving up no more than this share of them
RUN_LOOKBACK = 16              # score changes looked back over


def _score_changes(plays: list[Play]) -> list[Play]:
    changes, last = [], (0, 0)
    for item in plays:
        score = (item.away_score, item.home_score)
        if score != last:
            changes.append(item)
            last = score
    return changes


def scoring_run(plays: list[Play], away: str, home: str) -> str:
    """'ORL on a 9-2 run' when one team has heavily outscored the other up to now, else ''."""
    changes = _score_changes(plays)
    if len(changes) < 2:
        return ""
    latest, best = changes[-1], None
    for earlier in reversed(changes[-RUN_LOOKBACK - 1:-1]):
        scored = {away: latest.away_score - earlier.away_score,
                  home: latest.home_score - earlier.home_score}
        team = max(scored, key=scored.get)
        made, allowed = scored[team], min(scored.values())
        if made >= RUN_MIN_POINTS and allowed <= made * RUN_MAX_SHARE:
            if best is None or made - allowed > best[1] - best[2]:
                best = (team, made, allowed)
    return f"{best[0]} on a {best[1]}-{best[2]} run" if best else ""
