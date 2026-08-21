"""Soccer board: Poisson attack/defense predictions merged with
FanDuel three-way and totals lines, market-anchored like MLB."""

import datetime as dt

from .betting import ev, odds_math
from .data import football_data, odds_api
from .models import soccer
from .pipeline import MODEL_WEIGHT, SUSPECT_EDGE, _parse_iso


def build_league_model(league: str) -> tuple[soccer.LeagueModel, int]:
    today = dt.date.today()
    matches: list[soccer.Match] = []
    for code in football_data.season_codes(today.year, today.month):
        matches.extend(
            soccer.Match(m["home"], m["away"], m["home_goals"], m["away_goals"])
            for m in football_data.league_results(league, code)
        )
    return soccer.fit_league(matches), len(matches)


def build_soccer_board(league: str) -> list[dict]:
    model, matches_trained = build_league_model(league)
    events = odds_api.fanduel_soccer(league)
    now = dt.datetime.now(dt.timezone.utc)
    board = []
    for event in events:
        commence = _parse_iso(event.get("commence_time"))
        if commence is None or commence < now:
            continue
        row = _predict_match(event, model)
        if row is not None:
            board.append(row)
    board.sort(key=lambda r: r.get("best_ev") if r.get("best_ev") is not None else -1.0,
               reverse=True)
    return board, matches_trained


def _predict_match(event: dict, model: soccer.LeagueModel) -> dict | None:
    known = model.teams()
    home = football_data.map_team_name(event["home"], known)
    away = football_data.map_team_name(event["away"], known)
    if home is None or away is None:
        return None  # promoted team or name we can't bridge yet
    home_rate, away_rate = soccer.expected_goals(model, home, away)
    probs = soccer.match_probs(home_rate, away_rate)
    row = {
        "commence_time": event["commence_time"],
        "home": event["home"],
        "away": event["away"],
        "p_home": probs["home"],
        "p_draw": probs["draw"],
        "p_away": probs["away"],
        "model_total": home_rate + away_rate,
        "home_ml": event.get("home_ml"),
        "draw_ml": event.get("draw_ml"),
        "away_ml": event.get("away_ml"),
        "total_line": event.get("total_line"),
        "over_odds": event.get("over_odds"),
        "under_odds": event.get("under_odds"),
    }
    _attach_soccer_ev(row, home_rate, away_rate)
    return row


def _attach_soccer_ev(row: dict, home_rate: float, away_rate: float) -> None:
    row["suspect"] = False
    candidates = []
    if all(row.get(k) is not None for k in ("home_ml", "draw_ml", "away_ml")):
        fair = odds_math.devig_multiway([
            odds_math.implied_prob(row["home_ml"]),
            odds_math.implied_prob(row["draw_ml"]),
            odds_math.implied_prob(row["away_ml"]),
        ])
        model_probs = [row["p_home"], row["p_draw"], row["p_away"]]
        if max(abs(m - f) for m, f in zip(model_probs, fair)) > SUSPECT_EDGE:
            row["suspect"] = True
        blended = [MODEL_WEIGHT * m + (1 - MODEL_WEIGHT) * f
                   for m, f in zip(model_probs, fair)]
        row["p_home_bet"], row["p_draw_bet"], row["p_away_bet"] = blended
        candidates.extend([
            ("home_ev", blended[0], row["home_ml"]),
            ("draw_ev", blended[1], row["draw_ml"]),
            ("away_ev", blended[2], row["away_ml"]),
        ])
    if (row.get("total_line") is not None
            and row.get("over_odds") is not None
            and row.get("under_odds") is not None):
        probs = soccer.total_goals_probs(home_rate, away_rate, row["total_line"])
        fair_over, _ = odds_math.devig_two_way(
            odds_math.implied_prob(row["over_odds"]),
            odds_math.implied_prob(row["under_odds"]),
        )
        if abs(probs["over"] - fair_over) > SUSPECT_EDGE:
            row["suspect"] = True
        row["p_over_bet"] = MODEL_WEIGHT * probs["over"] + (1 - MODEL_WEIGHT) * fair_over
        row["p_under_bet"] = 1.0 - row["p_over_bet"]
        candidates.extend([
            ("over_ev", row["p_over_bet"], row["over_odds"]),
            ("under_ev", row["p_under_bet"], row["under_odds"]),
        ])
    best = None
    for key, prob, american in candidates:
        value = ev.ev_per_unit(prob, odds_math.american_to_decimal(american))
        row[key] = value
        if best is None or value > best:
            best = value
    row["best_ev"] = best
