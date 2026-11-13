"""NBA's free live feed: today's scoreboard and per-game box scores.

Public data from NBA's own site, no key and no quota. It only covers games
that are scheduled, in progress or just finished, and it can be slow or
unavailable, so every fetch turns failure into one LiveDataError the
screen can show instead of crashing.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace

import requests

SCHEDULED, LIVE, FINAL = 1, 2, 3
REQUEST_TIMEOUT = 10
_DURATION = re.compile(r"PT(?:(\d+)M)?(?:([\d.]+)S)?")


class LiveDataError(Exception):
    pass


def _fetch_payload(endpoint, *args, root: str) -> dict:
    """Request supported compression and retry an unreadable feed once."""
    from nba_api.live.nba.library.http import STATS_HEADERS

    # nba_api advertises Brotli even when requests has no Brotli decoder.
    # Compressed bytes then reach its JSON parser as text and fail to decode.
    headers = {**STATS_HEADERS, "Accept": "application/json",
               "Accept-Encoding": requests.utils.DEFAULT_ACCEPT_ENCODING}
    for attempt in range(2):
        try:
            payload = endpoint(*args, headers=headers, timeout=REQUEST_TIMEOUT).get_dict()
            if not isinstance(payload, dict) or not isinstance(payload.get(root), dict):
                raise ValueError("Missing live-feed data")
            if root == "scoreboard" and not isinstance(payload[root].get("games"), list):
                raise ValueError("Missing scoreboard games")
            return payload
        except (ValueError, requests.RequestException):
            if attempt:
                raise
            headers = {**headers, "Cache-Control": "no-cache", "Pragma": "no-cache"}
            _fresh_session()


def _fresh_session() -> None:
    """Give nba_api a new connection and an empty cookie jar for its next request.

    nba_api shares one session for the life of the process. A server that has been up for a
    while has been seen to get unreadable answers on every request while a newly started
    process, asking for the same thing, gets good ones; retrying on the same session cannot
    recover from that. The old session is left for any request still using it."""
    from nba_api.live.nba.library.http import NBALiveHTTP
    NBALiveHTTP.set_session(requests.Session())


def _failure_reason(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return "NBA returned an unreadable response after retrying"
    return type(exc).__name__


@dataclass(frozen=True)
class LiveGame:
    game_id: str
    status: int
    status_text: str
    period: int
    clock: str
    away: str
    home: str
    away_score: int
    home_score: int
    away_timeouts: int = 0
    home_timeouts: int = 0
    away_bonus: bool = False
    home_bonus: bool = False


@dataclass(frozen=True)
class PlayerLine:
    player_id: int
    name: str
    team: str
    points: int
    rebounds: int
    assists: int
    minutes: float
    played: bool
    on_court: bool
    starter: bool = False
    fg_made: int = 0
    fg_att: int = 0
    threes: int = 0          # 3-pointers made
    three_att: int = 0
    ft_made: int = 0
    ft_att: int = 0
    steals: int = 0
    blocks: int = 0
    turnovers: int = 0
    plus_minus: float = 0.0
    fouls: int = 0
    technicals: int = 0
    not_playing: str = ""    # the feed's reason when it lists a player as unavailable


@dataclass(frozen=True)
class Exit:
    """How a player left the floor, from the play-by-play: thrown out, or subbed out and not back."""
    ejected: bool = False
    out_period: int = 0              # period of a "sub out" with no "sub in" after it; 0 otherwise
    out_seconds_left: float = 0.0    # the period clock at that moment


@dataclass(frozen=True)
class Shot:
    team: str
    player: str
    made: bool
    x: float                 # 0-100 along the court's length
    y: float                 # 0-100 across its width
    period: int
    distance: float          # feet from the basket
    is_three: bool
    description: str


@dataclass(frozen=True)
class Play:
    order: int
    period: str            # "Q2", "OT1"
    clock: str             # "4:35"
    team: str              # tricode, or "" for a neutral event such as period end
    text: str
    score: str             # "CHI 28 - NYK 53"
    away_score: int = 0
    home_score: int = 0


LOGO_URL = "https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.svg"
REGULATION_PERIODS = 4


def team_ids() -> dict[str, int]:
    """Tricode -> NBA team id, from the offline list that ships with nba_api."""
    from nba_api.stats.static import teams
    return {team["abbreviation"]: team["id"] for team in teams.get_teams()}


def logo_url(tricode: str) -> str:
    """The NBA's own logo image for a team, or '' for an unknown tricode."""
    team_id = team_ids().get(tricode)
    return LOGO_URL.format(team_id=team_id) if team_id else ""


def period_label(period: int) -> str:
    return f"Q{period}" if period <= REGULATION_PERIODS else f"OT{period - REGULATION_PERIODS}"


QUARTER_NAMES = {1: "1st Qtr", 2: "2nd Qtr", 3: "3rd Qtr", 4: "4th Qtr"}


def period_status(label: str) -> str:
    """'Q3' -> '3rd Qtr', worded the way the scoreboard words it; 'OT1' stays 'OT1'."""
    if label.startswith("Q"):
        return QUARTER_NAMES.get(int(label[1:]), label)
    return label


def parse_playbyplay(payload: dict, away: str, home: str) -> list[Play]:
    """Plays in the order they happened. Plays with no description are dropped."""
    plays = []
    for action in payload.get("game", {}).get("actions", []):
        text = (action.get("description") or "").strip()
        if not text:
            continue
        away_score, home_score = int(action.get("scoreAway") or 0), int(action.get("scoreHome") or 0)
        plays.append(Play(
            order=int(action.get("orderNumber", action.get("actionNumber", 0))),
            period=period_label(int(action.get("period", 1))),
            clock=clock_from_duration(action.get("clock", "")),
            team=action.get("teamTricode") or "", text=text,
            score=f"{away} {away_score} - {home} {home_score}",
            away_score=away_score, home_score=home_score))
    return sorted(plays, key=lambda play: play.order)


def minutes_from_duration(duration: str) -> float:
    """'PT13M51.00S' -> 13.85. Empty or malformed input is 0."""
    match = _DURATION.fullmatch(duration or "")
    if not match:
        return 0.0
    return int(match.group(1) or 0) + float(match.group(2) or 0) / 60.0


def clock_from_duration(duration: str) -> str:
    """'PT01M25.00S' -> '1:25'. Empty when the clock isn't running."""
    match = _DURATION.fullmatch(duration or "")
    if not match or not duration:
        return ""
    return f"{int(match.group(1) or 0)}:{int(float(match.group(2) or 0)):02d}"


def parse_scoreboard(payload: dict) -> list[LiveGame]:
    games = []
    for game in payload.get("scoreboard", {}).get("games", []):
        away, home = game["awayTeam"], game["homeTeam"]
        games.append(LiveGame(
            game_id=game["gameId"], status=int(game["gameStatus"]),
            status_text=game["gameStatusText"].strip(), period=int(game.get("period", 0)),
            clock=clock_from_duration(game.get("gameClock", "")),
            away=away["teamTricode"], home=home["teamTricode"],
            away_score=int(away["score"]), home_score=int(home["score"]),
            away_timeouts=int(away.get("timeoutsRemaining") or 0),
            home_timeouts=int(home.get("timeoutsRemaining") or 0),
            away_bonus=bool(away.get("inBonus")), home_bonus=bool(home.get("inBonus"))))
    return games


def parse_boxscore(payload: dict) -> dict[int, PlayerLine]:
    """Every player listed for the game, keyed by NBA player id."""
    game = payload.get("game", {})
    lines = {}
    for side in ("awayTeam", "homeTeam"):
        team = game.get(side, {})
        for player in team.get("players", []):
            stats = player["statistics"]
            lines[int(player["personId"])] = PlayerLine(
                player_id=int(player["personId"]), name=player["name"],
                team=team["teamTricode"], points=int(stats["points"]),
                rebounds=int(stats["reboundsTotal"]), assists=int(stats["assists"]),
                minutes=minutes_from_duration(stats.get("minutes", "")),
                played=player.get("played") == "1", on_court=player.get("oncourt") == "1",
                starter=player.get("starter") == "1",
                fg_made=int(stats.get("fieldGoalsMade", 0)),
                fg_att=int(stats.get("fieldGoalsAttempted", 0)),
                threes=int(stats.get("threePointersMade", 0)),
                three_att=int(stats.get("threePointersAttempted", 0)),
                ft_made=int(stats.get("freeThrowsMade", 0)),
                ft_att=int(stats.get("freeThrowsAttempted", 0)),
                steals=int(stats.get("steals", 0)), blocks=int(stats.get("blocks", 0)),
                turnovers=int(stats.get("turnovers", 0)),
                plus_minus=float(stats.get("plusMinusPoints", 0.0)),
                fouls=int(stats.get("foulsPersonal", 0)),
                technicals=int(stats.get("foulsTechnical", 0)),
                not_playing=_reason(player))
    return lines


def _reason(player: dict) -> str:
    text = player.get("notPlayingDescription") or player.get("notPlayingReason") or ""
    return text.replace("_", " ").strip().capitalize()


def seconds_from_duration(duration: str) -> float:
    """'PT06M49.00S' -> 409.0. Empty or malformed input is 0."""
    return minutes_from_duration(duration) * 60.0


def parse_exits(payload: dict) -> dict[int, Exit]:
    """Per player: an ejection, or the last substitution out that no substitution in has answered."""
    exits: dict[int, Exit] = {}
    actions = sorted(payload.get("game", {}).get("actions", []),
                     key=lambda a: a.get("orderNumber", a.get("actionNumber", 0)))
    for action in actions:
        kind, player = action.get("actionType"), action.get("personId")
        if not player:
            continue
        before = exits.get(int(player), Exit())
        if kind == "ejection":
            exits[int(player)] = replace(before, ejected=True)
        elif kind == "substitution" and action.get("subType") == "out":
            exits[int(player)] = replace(before, out_period=int(action.get("period", 0)),
                                         out_seconds_left=seconds_from_duration(action.get("clock", "")))
        elif kind == "substitution" and action.get("subType") == "in":
            exits[int(player)] = replace(before, out_period=0, out_seconds_left=0.0)
    return exits


# the team numbers worth comparing, straight from the box score
TEAM_STAT_FIELDS = (
    "fieldGoalsMade", "fieldGoalsAttempted", "threePointersMade", "threePointersAttempted",
    "freeThrowsMade", "freeThrowsAttempted", "reboundsTotal", "reboundsOffensive", "assists",
    "steals", "blocks", "turnovers", "pointsInThePaint", "pointsFastBreak",
    "pointsSecondChance", "pointsFromTurnovers", "benchPoints", "biggestLead",
    "foulsPersonal", "points",
)


def parse_team_stats(payload: dict) -> dict[str, dict[str, float]]:
    """Each team's comparison numbers, keyed by tricode. A number the feed
    doesn't carry (it varies by game state) is simply left out."""
    game = payload.get("game", {})
    teams = {}
    for side in ("awayTeam", "homeTeam"):
        team = game.get(side)
        if team:
            stats = team.get("statistics", {})
            teams[team["teamTricode"]] = {
                field: float(stats[field]) for field in TEAM_STAT_FIELDS if field in stats}
    return teams


def parse_period_scores(payload: dict) -> dict[str, list[int]]:
    """Points by period for each team, keyed by tricode, covering only the
    periods that have been played or are being played."""
    game = payload.get("game", {})
    current = int(game.get("period") or 0)
    scores = {}
    for side in ("awayTeam", "homeTeam"):
        team = game.get(side)
        if team:
            scores[team["teamTricode"]] = [
                int(p["score"]) for p in team.get("periods", [])
                if int(p["period"]) <= max(current, 1)]
    return scores


def parse_shots(payload: dict) -> list[Shot]:
    """Every field-goal attempt that has a court location, in game order."""
    shots = []
    for action in payload.get("game", {}).get("actions", []):
        if action.get("isFieldGoal") != 1 or action.get("x") is None or action.get("y") is None:
            continue
        shots.append(Shot(
            team=action.get("teamTricode") or "", player=action.get("playerNameI") or "",
            made=action.get("shotResult") == "Made", x=float(action["x"]), y=float(action["y"]),
            period=int(action.get("period", 1)),
            distance=float(action.get("shotDistance") or 0.0),
            is_three=action.get("actionType") == "3pt",
            description=(action.get("description") or "").strip()))
    return shots


def fetch_games() -> list[LiveGame]:
    """Today's games with live scores."""
    from nba_api.live.nba.endpoints import scoreboard
    try:
        games = parse_scoreboard(_fetch_payload(scoreboard.ScoreBoard, root="scoreboard"))
    except Exception as exc:
        raise LiveDataError(f"NBA live scores are unavailable ({_failure_reason(exc)})") from None
    # The aggregate scoreboard can lag individual games at tip-off. Check every
    # scheduled game independently, so one game starting does not gate the others.
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(_confirm_start, games))


def _confirm_start(game: LiveGame) -> LiveGame:
    if game.status != SCHEDULED:
        return game
    from nba_api.live.nba.endpoints import boxscore
    try:
        payload = _fetch_payload(boxscore.BoxScore, game.game_id, root="game")["game"]
        return confirmed_status(game, payload)
    except Exception:
        # An unavailable pregame box is normal; it must not hide other games.
        return game


def confirmed_status(game: LiveGame, payload: dict) -> LiveGame:
    """Promote only from the same game's explicit status, never from the wall clock."""
    if payload.get("gameId") != game.game_id:
        return game
    status = int(payload.get("gameStatus", SCHEDULED))
    if game.status != SCHEDULED or status not in (LIVE, FINAL):
        return game
    return replace(game, status=status, status_text=payload.get("gameStatusText", "").strip(),
                   period=int(payload.get("period", 0)),
                   clock=clock_from_duration(payload.get("gameClock", "")),
                   away_score=int(payload["awayTeam"]["score"]),
                   home_score=int(payload["homeTeam"]["score"]))


def fetch_plays(game_id: str, away: str, home: str) -> list[Play]:
    """One game's play-by-play, oldest first."""
    from nba_api.live.nba.endpoints import playbyplay
    try:
        payload = _fetch_payload(playbyplay.PlayByPlay, game_id, root="game")
        return parse_playbyplay(payload, away, home)
    except Exception as exc:
        raise LiveDataError(f"The play-by-play is unavailable ({_failure_reason(exc)})") from None


@dataclass(frozen=True)
class GameDetail:
    """Everything the game center shows, from one box score and one
    play-by-play fetch."""
    players: dict[int, PlayerLine]
    team_stats: dict[str, dict[str, float]]
    period_scores: dict[str, list[int]]
    shots: list[Shot]
    plays: list[Play]
    exits: dict[int, Exit] = field(default_factory=dict)


def fetch_detail(game_id: str, away: str, home: str) -> GameDetail:
    from nba_api.live.nba.endpoints import boxscore, playbyplay
    try:
        box = _fetch_payload(boxscore.BoxScore, game_id, root="game")
        plays = _fetch_payload(playbyplay.PlayByPlay, game_id, root="game")
        return GameDetail(
            players=parse_boxscore(box), team_stats=parse_team_stats(box),
            period_scores=parse_period_scores(box), shots=parse_shots(plays),
            plays=parse_playbyplay(plays, away, home), exits=parse_exits(plays))
    except Exception as exc:
        raise LiveDataError(f"The game details are unavailable ({_failure_reason(exc)})") from None


def fetch_box(game_id: str) -> dict[int, PlayerLine]:
    """One game's box score."""
    from nba_api.live.nba.endpoints import boxscore
    try:
        return parse_boxscore(_fetch_payload(boxscore.BoxScore, game_id, root="game"))
    except Exception as exc:
        raise LiveDataError(f"The box score is unavailable ({_failure_reason(exc)})") from None
