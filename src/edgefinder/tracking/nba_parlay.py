"""Turns the NBA ledgers into parlay legs, and suggests slips.

A leg's probability is the model's chance blended 30/70 toward the market's
own number, the same anchoring every pick uses, because the raw model
probability is overconfident and a parlay multiplies that overconfidence.
Over/under legs come from the main ledger (both sides of each line); X+
legs come from the alternate-lines ledger.
"""

from itertools import combinations

import pandas as pd

from ..betting import correlated
from ..betting.correlated import Leg
from ..betting.ev import ev_per_unit
from ..betting.odds_math import american_to_decimal
from ..data import nba_players
from .nba_alt import MAX_DISAGREEMENT, MIN_MODEL_P
from .nba_paper import MODEL_WEIGHT

STAT = "points"           # the only stat the models project so far
COLUMNS = ["Leg", "Stat", "Game", "Player", "Side", "Odds", "Model %", "Market %", "Blended %",
           "Leg EV %", "player_id", "event_id", "is_over", "prob", "line",
           "away_abbr", "home_abbr"]
SUGGESTION_POOL = 16       # best legs considered when searching for slips
# A leg that is nearly certain ("3+ points" at -2000) pays almost nothing and only
# pads a slip. About -333 is the most a suggested leg may cost to back.
MIN_LEG_DECIMAL = 1.30
MIN_LEG_EV = 0.02


MODEL_NAMES = {
    "ewma-v1": "Simple: recent scoring average",
    "minutes-v1": "Smarter: projected minutes × scoring rate",
}
LIKELY = 0.6               # from here a chance reads better as "N in 10" than "1 in 1"
EVEN_BAND = 0.05          # slips within 5 cents per dollar of break-even read as "about even"


HEADSHOT_URL = "https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"


def headshot_url(player_id) -> str:
    """The NBA's own headshot image for a player id (the same id the game logs use)."""
    return HEADSHOT_URL.format(player_id=int(player_id))


def model_name(version: str) -> str:
    """Plain-language name for a model version; unknown versions pass through."""
    return MODEL_NAMES.get(version, version)


def one_in(probability: float) -> str:
    """'1 in 37' for a 2.7% chance, '9 in 10' for 89%: easier to feel than a percentage."""
    if probability <= 0.0:
        return "never"
    if probability >= LIKELY:
        return f"{round(probability * 10)} in 10"
    return f"1 in {max(1, round(1.0 / probability)):,}"


def verdict(ev_per_dollar: float) -> str:
    """One plain sentence on what a slip is worth, if the model is right."""
    cents = abs(ev_per_dollar) * 100.0
    if ev_per_dollar > EVEN_BAND:
        return (f"On these numbers it wins about {cents:.0f} cents per \\$1 over time. "
                "That only holds if the projection is right, and it hasn't been tested yet.")
    if ev_per_dollar < -EVEN_BAND:
        return f"On these numbers it loses about {cents:.0f} cents per \\$1 over time."
    return "On these numbers it's roughly break-even over time."


def toggle_leg(slip: list[int], index: int, player_ids) -> list[int]:
    """Tapping a price adds it; tapping it again removes it. A player can be on
    a slip only once, so adding a second price for him replaces the first.
    `player_ids` maps each bet's position to its player."""
    if index in slip:
        return [i for i in slip if i != index]
    return [i for i in slip if player_ids[i] != player_ids[index]] + [index]


def stake_outcomes(stake: float, decimal_odds: float, ev_per_unit: float) -> dict[str, float]:
    """What a stake means in dollars: what comes back, the profit if every bet
    hits, what's lost if not, and the average result per the model."""
    if stake < 0:
        raise ValueError("a stake can't be negative")
    return {
        "total_return": stake * decimal_odds,
        "profit_if_wins": stake * (decimal_odds - 1.0),
        "loss_if_misses": -stake,
        "expected_profit": stake * ev_per_unit,
    }


def money(amount: float, signed: bool = False) -> str:
    """'$12.50', or '+$12.50' / '-$3.00' when signed."""
    sign = "+" if signed and amount > 0 else "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def player_teams(games: pd.DataFrame) -> dict[int, str]:
    """Each player's most recent team, from the game logs."""
    latest = games.sort_values("game_date").groupby("player_id").tail(1)
    return {int(row.player_id): row.team for row in latest.itertuples()}


def candidate_legs(ledger: pd.DataFrame, alt_ledger: pd.DataFrame, game_date: str,
                   model_version: str) -> pd.DataFrame:
    """Every over, under and X+ leg one model priced on a date."""
    rows = _over_under_rows(ledger, game_date, model_version)
    rows += _x_plus_rows(alt_ledger, game_date, model_version)
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    table = pd.DataFrame(rows)
    table["Blended %"] = table["prob"] * 100.0
    table["Leg EV %"] = [
        ev_per_unit(p, american_to_decimal(o)) * 100.0
        for p, o in zip(table["prob"], table["Odds"])]
    return table[COLUMNS].sort_values(["Game", "Player", "Leg"]).reset_index(drop=True)


def _over_under_rows(ledger: pd.DataFrame, game_date: str, model_version: str) -> list[dict]:
    day = ledger[(ledger["game_date"] == game_date)
                 & (ledger["model_version"] == model_version)]
    rows = []
    for row in day.itertuples():
        for is_over, odds, model_p, market_p in (
                (True, row.over_odds, row.model_p_over, row.fair_p_over),
                (False, row.under_odds, 1 - row.model_p_over, 1 - row.fair_p_over)):
            side = "Over" if is_over else "Under"
            rows.append(_leg_row(
                f"{row.player} · {side} {row.line} {STAT}", row, side, odds, model_p,
                market_p, is_over, row.line))
    return rows


def _x_plus_rows(alt_ledger: pd.DataFrame, game_date: str, model_version: str) -> list[dict]:
    if alt_ledger.empty:
        return []
    day = alt_ledger[(alt_ledger["game_date"] == game_date)
                     & (alt_ledger["model_version"] == model_version)]
    return [
        _leg_row(f"{row.player} · {int(row.threshold)}+ {STAT}", row, f"{int(row.threshold)}+",
                 row.over_odds, row.model_p, row.market_p, True, row.threshold - 0.5)
        for row in day.itertuples()
    ]


def _leg_row(label, row, side, odds, model_p, market_p, is_over, line) -> dict:
    blended = MODEL_WEIGHT * model_p + (1 - MODEL_WEIGHT) * market_p
    return {"Leg": label, "Stat": STAT.capitalize(), "Game": f"{row.away} @ {row.home}",
            "Player": row.player,
            "Side": side, "Odds": odds, "Model %": model_p * 100.0,
            "Market %": market_p * 100.0, "prob": blended,
            "player_id": row.player_id, "event_id": row.event_id, "is_over": is_over,
            "line": line, "away_abbr": nba_players.team_abbreviation(row.away),
            "home_abbr": nba_players.team_abbreviation(row.home)}


def to_legs(chosen: pd.DataFrame, teams: dict[int, str]) -> list[Leg]:
    """Builder legs for the rows a user picked. A player whose team is
    unknown is treated as on his own team, so he only matches opponents."""
    return [
        Leg(player=row.Player, event_id=row.event_id,
            team=teams.get(int(row.player_id), f"?{row.player_id}"),
            is_over=bool(row.is_over), prob=float(row.prob),
            american_odds=float(row.Odds), label=row.Leg)
        for row in chosen.itertuples()
    ]


# How much risk a suggested slip may carry, as the least chance it must have of
# hitting. A slip multiplies its legs' chances, so a few ordinary legs shrink fast.
STYLES = {"Safer": 0.35, "Balanced": 0.20, "Bigger payouts": 0.08}
DEFAULT_STYLE = "Balanced"


def suggest_parlays(candidates: pd.DataFrame, max_legs: int = 3, top: int = 5,
                    min_chance: float = STYLES[DEFAULT_STYLE]) -> pd.DataFrame:
    """Best slips built from legs that are each worth betting on their own,
    at most one leg per game so the legs really are independent, keeping only
    slips that have at least `min_chance` of hitting. Empty if fewer than two
    games have such a leg, or nothing clears the bar.

    Each game offers two legs to build from: the one with the best expected
    profit (usually a long shot) and the likeliest one that is still worth
    betting, so a cautious style has something sensible to work with."""
    good = _worthwhile_legs(candidates)
    best_value = good.sort_values("Leg EV %", ascending=False).drop_duplicates("event_id")
    likeliest = good.sort_values("prob", ascending=False).drop_duplicates("event_id")
    pool = pd.concat([best_value, likeliest]).loc[lambda t: ~t.index.duplicated()]
    pool = pool.sort_values("Leg EV %", ascending=False).head(SUGGESTION_POOL)
    slips = []
    for size in range(2, max_legs + 1):
        for combo in combinations(pool.index, size):
            chosen = pool.loc[list(combo)]
            if chosen["event_id"].nunique() < size:
                continue                              # two legs from one game: not independent
            summary = correlated.summarise(to_legs(chosen, {}))
            if summary["joint_probability"] < min_chance:
                continue
            slips.append({
                "Slip": "  +  ".join(chosen["Leg"]), "Legs": size,
                "Chance %": summary["joint_probability"] * 100.0,
                "Pays": summary["decimal_odds"] - 1.0,
                "EV %": summary["ev_per_unit"] * 100.0,
                "bets": list(combo),          # positions in `candidates`, to load onto a slip
            })
    if not slips:
        return pd.DataFrame(columns=["Slip", "Legs", "Chance %", "Pays", "EV %", "bets"])
    return pd.DataFrame(slips).sort_values("EV %", ascending=False).head(top).reset_index(drop=True)


def _worthwhile_legs(candidates: pd.DataFrame) -> pd.DataFrame:
    """Legs with real expected value, inside the range the model can be trusted
    (the same guardrails X+ picks use)."""
    model = candidates["Model %"] / 100.0
    market = candidates["Market %"] / 100.0
    pays_enough = candidates["Odds"].map(american_to_decimal) >= MIN_LEG_DECIMAL
    return candidates[(candidates["Leg EV %"] >= MIN_LEG_EV * 100.0)
                      & (model >= MIN_MODEL_P)
                      & ((model - market).abs() <= MAX_DISAGREEMENT)
                      & pays_enough]
