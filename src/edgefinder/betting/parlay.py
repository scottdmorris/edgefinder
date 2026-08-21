"""Parlay math with honest expected-value accounting.

Legs are assumed independent. Same-game parlay legs are often
correlated, which makes the naive product probability wrong -- the UI
must warn about this.
"""

from dataclasses import dataclass

from .ev import ev_per_unit
from .odds_math import american_to_decimal


@dataclass(frozen=True)
class ParlayLeg:
    description: str
    model_prob: float       # your model's true probability for the leg
    american_odds: float    # the sportsbook's quoted price for the leg


def parlay_true_prob(legs: list[ParlayLeg]) -> float:
    """Probability that every leg hits (independence assumed)."""
    prob = 1.0
    for leg in legs:
        prob *= leg.model_prob
    return prob


def parlay_decimal_odds(legs: list[ParlayLeg]) -> float:
    """Standard parlay payout: product of each leg's decimal odds."""
    decimal = 1.0
    for leg in legs:
        decimal *= american_to_decimal(leg.american_odds)
    return decimal


def parlay_ev(legs: list[ParlayLeg], quoted_decimal: float | None = None) -> float:
    """EV per unit staked for the whole parlay.

    quoted_decimal overrides the naive product payout when the book
    quotes something different (FanDuel SGP pricing usually pays less
    than the product).
    """
    if not legs:
        return 0.0
    payout = quoted_decimal if quoted_decimal is not None else parlay_decimal_odds(legs)
    return ev_per_unit(parlay_true_prob(legs), payout)


def leg_marginal_ev(legs: list[ParlayLeg], index: int) -> float:
    """How much adding legs[index] changed the parlay's EV.

    Positive means the leg improved the ticket; negative means it is
    dragging the ticket down and should probably be a separate bet or
    dropped.
    """
    if not 0 <= index < len(legs):
        raise IndexError("leg index out of range")
    without = [leg for i, leg in enumerate(legs) if i != index]
    if not without:
        return parlay_ev(legs)
    return parlay_ev(legs) - parlay_ev(without)
