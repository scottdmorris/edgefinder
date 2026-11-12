"""The Live screen's data: tonight's games, one game in full, and how a slip is doing.

Everything comes from NBA's free live feed (no key, no Odds API requests), fetched at most once
every few seconds however many people have the page open. Live games take their score and clock
from the latest play, because NBA's scoreboard can trail its own play-by-play by a minute.
"""

import datetime as dt
from dataclasses import replace

from ..data import nba_live
from ..data.nba_live import GameDetail, LiveGame
from ..tracking import nba_game_view as view
from ..tracking import nba_parlay, nba_slip_tracker
from ..ui import team_colors
from . import service

FEED_SECONDS = 8             # the page refreshes every 10s; each refresh then gets a new read
PLAYS_SHOWN = 40
STATES = {nba_live.SCHEDULED: "upcoming", nba_live.LIVE: "live", nba_live.FINAL: "final"}
ORDER = {nba_live.LIVE: 0, nba_live.SCHEDULED: 1, nba_live.FINAL: 2}


# ---- the feed, cached ----------------------------------------------------------------------------

def _received(fetch):
    value = fetch()
    return {"value": value, "received_at": dt.datetime.now(dt.timezone.utc).isoformat()}


def _scoreboard_feed() -> dict:
    return service.cached(("live", "games"), lambda: _received(nba_live.fetch_games), FEED_SECONDS)


def _scoreboard() -> list[LiveGame]:
    return _scoreboard_feed()["value"]


def _detail_feed(game: LiveGame) -> dict:
    return service.cached(("live", "detail", game.game_id),
                          lambda: _received(lambda: nba_live.fetch_detail(
                              game.game_id, game.away, game.home)), FEED_SECONDS)


def _detail(game: LiveGame) -> GameDetail | None:
    try:
        return _detail_feed(game)["value"]
    except nba_live.LiveDataError:
        return None


def _box(game_id: str) -> dict:
    return service.cached(("live", "box", game_id), lambda: nba_live.fetch_box(game_id),
                          FEED_SECONDS)


def freshest(game: LiveGame, detail: GameDetail | None) -> LiveGame:
    """A live game's score and clock from its latest play, when there is one."""
    if game.status != nba_live.LIVE or detail is None or not detail.plays:
        return game
    latest = detail.plays[-1]
    return replace(game, away_score=latest.away_score, home_score=latest.home_score,
                   status_text=nba_live.period_status(latest.period), clock=latest.clock,
                   period=_period_number(latest.period) or game.period)


def _period_number(label: str) -> int:
    """'Q3' -> 3, 'OT1' -> 5; 0 when the label is neither."""
    if label.startswith("Q") and label[1:].isdigit():
        return int(label[1:])
    if label.startswith("OT") and label[2:].isdigit():
        return nba_live.REGULATION_PERIODS + int(label[2:])
    return 0


def current_games() -> list[tuple[LiveGame, GameDetail | None]]:
    """Every game on the board with its detail (live games only), games on now first."""
    pairs = []
    for game in _scoreboard():
        detail = _detail(game) if game.status == nba_live.LIVE else None
        pairs.append((freshest(game, detail), detail))
    return sorted(pairs, key=lambda pair: ORDER.get(pair[0].status, 3))


# ---- shaping ---------------------------------------------------------------------------------------

def _status(game: LiveGame) -> str:
    running = game.status == nba_live.LIVE and ("Qtr" in game.status_text
                                                 or game.status_text.startswith("OT"))
    return f"{game.status_text} {game.clock}".strip() if running else game.status_text


def _side(game: LiveGame, team: str, color: str, detail: GameDetail | None) -> dict:
    away = team == game.away
    fouls = detail.team_stats.get(team, {}).get("foulsPersonal") if detail else None
    return {
        "team": team, "logo": nba_live.logo_url(team), "color": color,
        "score": game.away_score if away else game.home_score,
        "timeouts": game.away_timeouts if away else game.home_timeouts,
        "bonus": game.away_bonus if away else game.home_bonus,
        "fouls": None if fouls is None else int(fouls),
    }


def game_card(game: LiveGame, detail: GameDetail | None = None) -> dict:
    away_color, home_color = team_colors.matchup_colors(game.away, game.home)
    return {
        "id": game.game_id, "state": STATES.get(game.status, "upcoming"),
        "status": _status(game),
        "received_at": _scoreboard_feed()["received_at"],
        "detail_received_at": _detail_feed(game)["received_at"] if detail is not None else None,
        "detail_available": detail is not None,
        "away": _side(game, game.away, away_color, detail),
        "home": _side(game, game.home, home_color, detail),
    }


def _period(period: int) -> str:
    return f"Q{period}" if period <= 4 else f"OT{period - 4}"


def _shots(game: LiveGame, detail: GameDetail) -> list[dict]:
    placed = view.to_ends(detail.shots, game.away, game.home)
    return [{"n": i, "team": s.team, "x": round(p.x, 2), "y": round(p.y, 2), "made": s.made,
             "three": s.is_three, "period": s.period, "period_label": _period(s.period),
             "text": f"{s.player} · {'made' if s.made else 'missed'} · {s.distance:.0f} ft"}
            for i, (s, p) in enumerate(zip(detail.shots, placed))]


def _player(p, team: str) -> dict:
    return {"id": p.player_id, "name": p.name, "photo": nba_parlay.headshot_url(p.player_id),
            "team": team}


def _leaders(game: LiveGame, detail: GameDetail) -> list[dict]:
    out = []
    for team in (game.away, game.home):
        for stat, p in view.leaders(detail.players, team).items():
            if p is not None:
                value = {"Points": p.points, "Rebounds": p.rebounds, "Assists": p.assists}[stat]
                out.append({**_player(p, team), "stat": stat, "value": value})
    return out


def _box_groups(players: dict, team: str) -> dict:
    groups = {}
    for name, starters in (("starters", True), ("bench", False)):
        table = view.box_table(players, team, starters)
        on_court = {p.player_id for p in players.values() if p.on_court}
        rows = []
        for record in table.to_dict("records"):
            pid = int(record.pop("player_id"))
            record["Player"] = record["Player"].replace("  🏀", "")
            rows.append({"id": pid, "photo": nba_parlay.headshot_url(pid),
                         "on_court": pid in on_court, **record})
        groups[name] = rows
    return groups


def game_detail(game_id: str) -> dict:
    """One game in full: header, quarters, shots, team stats, leaders, plays and box score."""
    pair = next(((g, d) for g, d in current_games() if g.game_id == game_id), None)
    if pair is None:
        raise service.NotFound(f"no game {game_id} on tonight's board")
    game, detail = pair
    if game.status == nba_live.FINAL:
        detail = _detail(game)                  # a final game: its box score still matters
    card = game_card(game, detail)
    if detail is None:
        return {**card, "detail": None}
    quarters = view.quarter_table(detail.period_scores, game.away, game.home,
                                  game.away_score, game.home_score)
    trouble = [{"name": name, "fouls": count, "team": team}
               for team in (game.away, game.home)
               for name, count in view.foul_trouble(detail.players, team)]
    return {**card, "detail": {
        "quarters": {"columns": list(quarters.columns),
                     "rows": [{"team": team, "values": [int(v) for v in values]}
                              for team, values in zip(quarters.index, quarters.values)]},
        "shots": _shots(game, detail),
        "compare": view.comparison_rows(detail.team_stats.get(game.away, {}),
                                        detail.team_stats.get(game.home, {})),
        "leaders": _leaders(game, detail),
        "plays": [{"order": p.order, "period": p.period, "clock": p.clock, "team": p.team,
                   "text": p.text, "score": p.score}
                  for p in reversed(detail.plays[-PLAYS_SHOWN:])],
        "box": {game.away: _box_groups(detail.players, game.away),
                game.home: _box_groups(detail.players, game.home)},
        "foul_trouble": trouble,
    }}


def board() -> list[dict]:
    return [game_card(g, d) for g, d in current_games()]


def _alert(row, game: LiveGame | None, detail: GameDetail | None) -> str:
    """A warning for a bet still in play whose player looks done for the night."""
    if game is None or detail is None or row.Status != nba_slip_tracker.ALIVE:
        return ""
    return nba_slip_tracker.exit_alert(detail.players.get(int(row.player_id)),
                                       detail.exits.get(int(row.player_id)), game)


def track(date: str | None, book: str | None, model: str | None, leg_ids: list[int]) -> dict:
    """How each bet on a slip is doing right now, and the slip overall."""
    table, market = service.candidates(date, book, model)
    missing = [i for i in leg_ids if i not in table.index]
    if missing:
        raise service.NotFound("Some saved selections are no longer on the board. Review the slip on the Parlay screen.")
    if not leg_ids:
        return {"status": nba_slip_tracker.NOT_STARTED, "legs": []}
    if market["date"] != service.today().isoformat():
        raise ValueError("Live tracking is available only for today's game day. This saved slip is from "
                         + market["date"] + "; its result cannot be inferred from today's games.")
    chosen = table.loc[leg_ids]
    pairs = current_games()
    games = [g for g, _ in pairs]
    details = {g.game_id: d for g, d in pairs if d is not None}
    progress = nba_slip_tracker.track_slip(chosen, games, _box)
    legs = []
    for leg_id, row in zip(leg_ids, progress.itertuples()):
        player, bet = row.Leg.split(" · ", 1)
        selection = chosen.loc[leg_id]
        game = nba_slip_tracker.find_game(games, selection.away_abbr, selection.home_abbr)
        legs.append({"id": leg_id, "player": player, "bet": bet,
                     "alert": _alert(row, game, details.get(game.game_id) if game else None),
                     "game_id": game.game_id if game else None,
                     "game_state": STATES.get(game.status, "upcoming") if game else None,
                     "photo": nba_parlay.headshot_url(row.player_id), "status": row.Status,
                     "have": None if row.Have is None or row.Have != row.Have else int(row.Have),
                     "target": int(row.Target), "progress": float(row.Progress),
                     "detail": row.Detail, "game": row.Game})
    return {"status": nba_slip_tracker.slip_status([leg["status"] for leg in legs]),
            "legs": legs}
