"""Data-driven parlay suggestions from the daily board.

Two modes, depending on what data is available:

- **Odds mode** (FanDuel lines loaded): only individually +EV legs are
  eligible, combos are ranked by total parlay EV, and if nothing +EV
  exists the suggester returns nothing rather than inventing a ticket.
- **Confidence mode** (no odds key): legs are ranked by model
  probability and combos by hit probability, with fair odds attached
  so the user can compare against FanDuel's quoted payout — a quote
  paying more than fair is +EV.

Legs from the same game are never combined (they are correlated, which
breaks the independence math).
"""

from dataclasses import dataclass
from itertools import combinations

from .ev import ev_per_unit
from .odds_math import american_to_decimal

MAX_LEG_POOL = 12          # cap the pool so combinations stay cheap
DEFAULT_TOP_N = 5
MIN_CONFIDENCE_PROB = 0.55  # confidence mode: only clear model favorites
MAX_LEG_REUSE = 2          # a leg may appear in at most this many suggestions


@dataclass(frozen=True)
class CandidateLeg:
    game_key: str
    description: str
    model_prob: float
    american_odds: float | None   # None when no market odds available
    ev: float | None              # None when no market odds available


@dataclass(frozen=True)
class SuggestedParlay:
    legs: tuple[CandidateLeg, ...]
    true_prob: float
    decimal_odds: float | None    # None in confidence mode
    ev: float | None              # None in confidence mode


def board_candidate_legs(board: list[dict]) -> list[CandidateLeg]:
    """Extract every biddable leg from board rows built by the pipeline."""
    legs = []
    for game in board:
        if game.get("status") not in (None, "Preview"):
            continue  # game already live or final: nothing left to bet
        if game.get("suspect"):
            continue  # implausible model-vs-market gap: data problem
        key = f"{game['away']} @ {game['home']}"
        legs.append(CandidateLeg(
            key, f"{game['home']} ML ({key})",
            game.get("p_home_bet", game["p_home"]),
            game.get("home_ml"), game.get("home_ml_ev"),
        ))
        legs.append(CandidateLeg(
            key, f"{game['away']} ML ({key})",
            game.get("p_away_bet", game["p_away"]),
            game.get("away_ml"), game.get("away_ml_ev"),
        ))
        legs.extend(_total_legs(game, key))
    return legs


def _total_legs(game: dict, key: str) -> list[CandidateLeg]:
    """Totals legs exist only when a market line is present to bet into.

    Uses market-blended probabilities when the pipeline attached them.
    """
    line = game.get("total_line")
    if line is None or game.get("over_ev") is None:
        return []
    if "p_over_bet" in game:
        over_prob, under_prob = game["p_over_bet"], game["p_under_bet"]
    else:
        from . import poisson

        probs = poisson.no_push_probs(line, game["model_total"])
        over_prob, under_prob = probs["over"], probs["under"]
    return [
        CandidateLeg(key, f"Over {line} ({key})", over_prob,
                     game.get("over_odds"), game.get("over_ev")),
        CandidateLeg(key, f"Under {line} ({key})", under_prob,
                     game.get("under_odds"), game.get("under_ev")),
    ]


def suggest_parlays(
    legs: list[CandidateLeg],
    num_legs: int = 3,
    top_n: int = DEFAULT_TOP_N,
    min_leg_ev: float = 0.0,
    min_confidence_prob: float = MIN_CONFIDENCE_PROB,
) -> list[SuggestedParlay]:
    if num_legs < 2:
        raise ValueError("A parlay needs at least 2 legs")
    odds_mode = any(leg.american_odds is not None for leg in legs)
    pool = _build_pool(legs, odds_mode, min_leg_ev, min_confidence_prob)
    suggestions = []
    for combo in combinations(pool, num_legs):
        if len({leg.game_key for leg in combo}) < num_legs:
            continue
        suggestions.append(_score_combo(combo, odds_mode))
    key = (lambda s: s.ev) if odds_mode else (lambda s: s.true_prob)
    suggestions.sort(key=key, reverse=True)
    if odds_mode:
        suggestions = [s for s in suggestions if s.ev > 0.0]
    return _diversify(suggestions, top_n)


def _diversify(suggestions: list[SuggestedParlay], top_n: int) -> list[SuggestedParlay]:
    """Keep the ranking but stop one strong leg from dominating every
    ticket, so the user sees genuinely different parlays."""
    selected: list[SuggestedParlay] = []
    usage: dict[str, int] = {}
    for suggestion in suggestions:
        if any(usage.get(leg.description, 0) >= MAX_LEG_REUSE
               for leg in suggestion.legs):
            continue
        selected.append(suggestion)
        for leg in suggestion.legs:
            usage[leg.description] = usage.get(leg.description, 0) + 1
        if len(selected) == top_n:
            break
    return selected


def _build_pool(
    legs: list[CandidateLeg],
    odds_mode: bool,
    min_leg_ev: float,
    min_confidence_prob: float,
) -> list[CandidateLeg]:
    if odds_mode:
        pool = [
            leg for leg in legs
            if leg.american_odds is not None
            and leg.ev is not None and leg.ev > min_leg_ev
        ]
        pool.sort(key=lambda leg: leg.ev, reverse=True)
    else:
        pool = [leg for leg in legs if leg.model_prob >= min_confidence_prob]
        pool.sort(key=lambda leg: leg.model_prob, reverse=True)
    return pool[:MAX_LEG_POOL]


def _score_combo(
    combo: tuple[CandidateLeg, ...], odds_mode: bool,
) -> SuggestedParlay:
    true_prob = 1.0
    for leg in combo:
        true_prob *= leg.model_prob
    if not odds_mode:
        return SuggestedParlay(combo, true_prob, None, None)
    decimal = 1.0
    for leg in combo:
        decimal *= american_to_decimal(leg.american_odds)
    return SuggestedParlay(combo, true_prob, decimal,
                           ev_per_unit(true_prob, decimal))
