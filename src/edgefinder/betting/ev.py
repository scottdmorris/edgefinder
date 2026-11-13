"""Expected value and Kelly bet sizing."""

DEFAULT_KELLY_MULTIPLIER = 0.25  # quarter Kelly: standard variance control
MAX_BANKROLL_FRACTION = 0.05     # never stake more than 5% on one bet


def ev_per_unit(true_prob: float, decimal_odds: float) -> float:
    """Expected profit per 1 unit staked. Positive means +EV."""
    win_profit = decimal_odds - 1.0
    return true_prob * win_profit - (1.0 - true_prob)


def kelly_fraction(true_prob: float, decimal_odds: float) -> float:
    """Full-Kelly optimal fraction of bankroll. 0 if the bet is -EV."""
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    fraction = (true_prob * b - (1.0 - true_prob)) / b
    return max(0.0, fraction)


def recommended_stake(
    bankroll: float,
    true_prob: float,
    decimal_odds: float,
    kelly_multiplier: float = DEFAULT_KELLY_MULTIPLIER,
    max_fraction: float = MAX_BANKROLL_FRACTION,
) -> float:
    """Fractional-Kelly stake, capped at max_fraction of bankroll."""
    if bankroll <= 0:
        return 0.0
    fraction = kelly_fraction(true_prob, decimal_odds) * max(kelly_multiplier, 0.0)
    fraction = max(0.0, min(fraction, max_fraction))
    return round(bankroll * fraction, 2)
