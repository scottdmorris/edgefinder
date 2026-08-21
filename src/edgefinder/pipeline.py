"""Builds the daily MLB board: model predictions merged with FanDuel
odds, ranked by expected value."""

import datetime as dt

from .betting import ev, odds_math, poisson
from .data import mlb_api, odds_api
from .models import elo, mlb

# an odds event must start within this window of the scheduled game
# time to be treated as the same game (series play the same matchup on
# consecutive days)
MAX_MATCH_WINDOW_SECONDS = 6 * 3600

# if the model disagrees with the devigged market by more than this,
# it is almost certainly a data problem (or the market knows something
# the model doesn't, e.g. a scratched starter) -- never a real edge
SUSPECT_EDGE = 0.15

# betting probabilities are shrunk toward the devigged market price:
# the market embeds injuries, lineups, and weather the model can't see.
# A v1 model earns only minority weight; raise this only after CLV
# tracking proves the model beats closing lines.
MODEL_WEIGHT = 0.30


def _blend(model_prob: float, market_fair_prob: float) -> float:
    return MODEL_WEIGHT * model_prob + (1.0 - MODEL_WEIGHT) * market_fair_prob


def build_mlb_state(season: int) -> dict:
    """Train Elo + run rates from the season's completed games."""
    results = mlb_api.season_results(season)
    model = elo.EloModel(k=elo.MLB_K, home_advantage=elo.MLB_HOME_ADVANTAGE)
    model.train([
        elo.GameResult(g["home"], g["away"], g["home_score"], g["away_score"])
        for g in results
    ])
    run_rates = _run_rates(results)
    return {"elo": model, "run_rates": run_rates, "games_trained": len(results)}


def _run_rates(results: list[dict]) -> dict[str, mlb.TeamRunRates]:
    scored: dict[str, list[int]] = {}
    allowed: dict[str, list[int]] = {}
    for g in results:
        scored.setdefault(g["home"], []).append(g["home_score"])
        allowed.setdefault(g["home"], []).append(g["away_score"])
        scored.setdefault(g["away"], []).append(g["away_score"])
        allowed.setdefault(g["away"], []).append(g["home_score"])
    return {
        team: mlb.TeamRunRates(
            scored_per_game=sum(scored[team]) / len(scored[team]),
            allowed_per_game=sum(allowed[team]) / len(allowed[team]),
        )
        for team in scored
    }


def build_board(season: int, date_iso: str) -> list[dict]:
    """One row per scheduled game with model probs, market odds, and EV."""
    state = build_mlb_state(season)
    schedule = mlb_api.todays_schedule(date_iso)
    odds_by_matchup = _index_odds(odds_api.fanduel_odds("mlb"))
    board = []
    for game in schedule:
        if not game["home"] or not game["away"]:
            continue
        row = _predict_game(game, state, season)
        candidates = odds_by_matchup.get((game["home"], game["away"]), [])
        match = _match_event(candidates, game.get("game_time"))
        if match is not None:
            row.update({key: match[key] for key in (
                "home_ml", "away_ml", "total_line", "over_odds", "under_odds",
            )})
        _attach_ev(row)
        board.append(row)
    board.sort(key=lambda r: r.get("best_ev") if r.get("best_ev") is not None else -1.0, reverse=True)
    return board


def _predict_game(game: dict, state: dict, season: int) -> dict:
    home_era = _starter_era(game.get("home_pitcher"), season)
    away_era = _starter_era(game.get("away_pitcher"), season)
    elo_prob = state["elo"].expected_home_win_prob(game["home"], game["away"])
    p_home = mlb.pitcher_adjusted_win_prob(elo_prob, home_era, away_era)
    home_rates = state["run_rates"].get(game["home"])
    away_rates = state["run_rates"].get(game["away"])
    total = None
    if home_rates and away_rates:
        total = mlb.expected_game_total(home_rates, away_rates, home_era, away_era)
    return {
        "game_time": game.get("game_time"),
        "status": game.get("status"),
        "home": game["home"],
        "away": game["away"],
        "home_pitcher": (game.get("home_pitcher") or {}).get("name"),
        "away_pitcher": (game.get("away_pitcher") or {}).get("name"),
        "home_era": home_era,
        "away_era": away_era,
        "p_home": p_home,
        "p_away": 1.0 - p_home,
        "model_total": total,
    }


def _starter_era(pitcher: dict | None, season: int) -> float | None:
    if not pitcher or not pitcher.get("id"):
        return None
    try:
        return mlb_api.pitcher_season_era(pitcher["id"], season)
    except mlb_api.MlbApiError:
        return None


def _parse_iso(timestamp: str | None) -> dt.datetime | None:
    if not timestamp:
        return None
    try:
        return dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _index_odds(events: list[dict]) -> dict[tuple, list[dict]]:
    """Group pregame events by matchup. Events that have already
    started are dropped: in-play odds must never be compared against a
    pregame model."""
    now = dt.datetime.now(dt.timezone.utc)
    index: dict[tuple, list[dict]] = {}
    for event in events:
        commence = _parse_iso(event.get("commence_time"))
        if commence is None or commence < now:
            continue  # unknown start time is unusable: could be in-play
        index.setdefault((event["home"], event["away"]), []).append(event)
    return index


def _match_event(candidates: list[dict], game_time_iso: str | None) -> dict | None:
    """Pick the odds event whose start time matches this scheduled game."""
    if not candidates:
        return None
    game_time = _parse_iso(game_time_iso)
    if game_time is None:
        return candidates[0]
    best, best_diff = None, None
    for event in candidates:
        commence = _parse_iso(event.get("commence_time"))
        if commence is None:
            continue
        diff = abs((commence - game_time).total_seconds())
        if best_diff is None or diff < best_diff:
            best, best_diff = event, diff
    if best is None or best_diff > MAX_MATCH_WINDOW_SECONDS:
        return None
    return best


def _attach_ev(row: dict) -> None:
    """Compute EV per unit for each available market side, and flag the
    row as suspect when model and market disagree implausibly."""
    row["suspect"] = False
    candidates = []
    if row.get("home_ml") is not None and row.get("away_ml") is not None:
        fair_home, _ = odds_math.devig_two_way(
            odds_math.implied_prob(row["home_ml"]),
            odds_math.implied_prob(row["away_ml"]),
        )
        if abs(row["p_home"] - fair_home) > SUSPECT_EDGE:
            row["suspect"] = True
        row["p_home_bet"] = _blend(row["p_home"], fair_home)
        row["p_away_bet"] = 1.0 - row["p_home_bet"]
        candidates.append(("home_ml_ev", row["p_home_bet"], row["home_ml"]))
        candidates.append(("away_ml_ev", row["p_away_bet"], row["away_ml"]))
    if row.get("total_line") is not None and row.get("model_total") is not None:
        probs = poisson.no_push_probs(row["total_line"], row["model_total"])
        if row.get("over_odds") is not None and row.get("under_odds") is not None:
            fair_over, _ = odds_math.devig_two_way(
                odds_math.implied_prob(row["over_odds"]),
                odds_math.implied_prob(row["under_odds"]),
            )
            if abs(probs["over"] - fair_over) > SUSPECT_EDGE:
                row["suspect"] = True
            row["p_over_bet"] = _blend(probs["over"], fair_over)
            row["p_under_bet"] = 1.0 - row["p_over_bet"]
            candidates.append(("over_ev", row["p_over_bet"], row["over_odds"]))
            candidates.append(("under_ev", row["p_under_bet"], row["under_odds"]))
    best = None
    for key, prob, american in candidates:
        value = ev.ev_per_unit(prob, odds_math.american_to_decimal(american))
        row[key] = value
        if best is None or value > best:
            best = value
    row["best_ev"] = best
