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
from .nba_alt import MAX_DISAGREEMENT, MIN_MODEL_P
from .nba_paper import MODEL_WEIGHT

STAT = "points"           # the only stat the models project so far
COLUMNS = ["Leg", "Stat", "Game", "Player", "Side", "Odds", "Model %", "Market %", "Blended %",
           "Leg EV %", "player_id", "event_id", "is_over", "prob"]
SUGGESTION_POOL = 14       # best legs considered when searching for slips
MIN_LEG_EV = 0.02


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
                market_p, is_over))
    return rows


def _x_plus_rows(alt_ledger: pd.DataFrame, game_date: str, model_version: str) -> list[dict]:
    if alt_ledger.empty:
        return []
    day = alt_ledger[(alt_ledger["game_date"] == game_date)
                     & (alt_ledger["model_version"] == model_version)]
    return [
        _leg_row(f"{row.player} · {int(row.threshold)}+ {STAT}", row, f"{int(row.threshold)}+",
                 row.over_odds, row.model_p, row.market_p, True)
        for row in day.itertuples()
    ]


def _leg_row(label, row, side, odds, model_p, market_p, is_over) -> dict:
    blended = MODEL_WEIGHT * model_p + (1 - MODEL_WEIGHT) * market_p
    return {"Leg": label, "Stat": STAT.capitalize(), "Game": f"{row.away} @ {row.home}",
            "Player": row.player,
            "Side": side, "Odds": odds, "Model %": model_p * 100.0,
            "Market %": market_p * 100.0, "prob": blended,
            "player_id": row.player_id, "event_id": row.event_id, "is_over": is_over}


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


def suggest_parlays(candidates: pd.DataFrame, max_legs: int = 3, top: int = 5) -> pd.DataFrame:
    """Best slips built from legs that are each worth betting on their own,
    at most one leg per game so the legs really are independent. Empty if
    fewer than two games have such a leg."""
    good = _worthwhile_legs(candidates)
    best_per_game = good.sort_values("Leg EV %", ascending=False).drop_duplicates("event_id")
    pool = best_per_game.head(SUGGESTION_POOL)
    slips = []
    for size in range(2, max_legs + 1):
        for combo in combinations(pool.index, size):
            chosen = pool.loc[list(combo)]
            summary = correlated.summarise(to_legs(chosen, {}))
            slips.append({
                "Slip": "  +  ".join(chosen["Leg"]), "Legs": size,
                "Chance %": summary["joint_probability"] * 100.0,
                "Pays": summary["decimal_odds"] - 1.0,
                "EV %": summary["ev_per_unit"] * 100.0,
            })
    if not slips:
        return pd.DataFrame(columns=["Slip", "Legs", "Chance %", "Pays", "EV %"])
    return pd.DataFrame(slips).sort_values("EV %", ascending=False).head(top).reset_index(drop=True)


def _worthwhile_legs(candidates: pd.DataFrame) -> pd.DataFrame:
    """Legs with real expected value, inside the range the model can be trusted
    (the same guardrails X+ picks use)."""
    model = candidates["Model %"] / 100.0
    market = candidates["Market %"] / 100.0
    return candidates[(candidates["Leg EV %"] >= MIN_LEG_EV * 100.0)
                      & (model >= MIN_MODEL_P)
                      & ((model - market).abs() <= MAX_DISAGREEMENT)]
