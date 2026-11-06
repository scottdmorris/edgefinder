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
from ..models import nba_recalibration, nba_stat_model
from .nba_alt import MAX_DISAGREEMENT, MIN_MODEL_P
from .nba_paper import MODEL_WEIGHT

STAT = "points"           # the default stat
BOOK = "fanduel"          # the default price source
DEFAULTS = {"stat": STAT, "book": BOOK}      # what an old ledger row without the column means
COLUMNS = ["Leg", "Stat", "stat_key", "Game", "Player", "Side", "Odds", "Model %", "Market %", "Blended %",
           "Leg EV %", "player_id", "event_id", "is_over", "prob", "line",
           "away_abbr", "home_abbr"]
SUGGESTION_POOL = 16       # best legs considered when searching for slips
SAME_GAME_POOL = 10        # inside one game, fewer: every combination is priced with correlations
# Different players' bets in one game move together only a little (the measured values
# are at most 0.09), so a slip whose plain product of chances is well short of the bar
# cannot clear it once correlated, and is skipped before the slow pricing.
PRUNE_BELOW = 0.85
# Safe "lock" legs (say -400) may sit on a slip: each one still has to be worth betting
# on its own. But a leg that is nearly certain ("3+ points" at -2000) pays almost nothing
# and only pads a slip, so about -1000 is the most a suggested leg may cost to back.
MIN_LEG_DECIMAL = 1.10
MIN_LEG_EV = 0.02


MODEL_NAMES = {
    "ewma-v1": "Simple: recent scoring average",
    "minutes-v1": "Smarter: projected minutes × scoring rate",
    "context-v1": "Smartest: adds who's out, the opponent and pace",
    "context-v2": "Sharpest: adds shot habits, blends two views, and sizes the uncertainty "
                  "to each player",
}
LIKELY = 0.6               # from here a chance reads better as "N in 10" than "1 in 1"
EVEN_BAND = 0.05          # slips within 5 cents per dollar of break-even read as "about even"


HEADSHOT_URL = "https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"


def headshot_url(player_id) -> str:
    """The NBA's own headshot image for a player id (the same id the game logs use)."""
    return HEADSHOT_URL.format(player_id=int(player_id))


SHORT_MODEL_NAMES = {"ewma-v1": "Simple", "minutes-v1": "Smarter", "context-v1": "Smartest",
                      "context-v2": "Sharpest"}


def short_model_name(version: str) -> str:
    """One-word chip label for a model version; unknown versions pass through."""
    return SHORT_MODEL_NAMES.get(version, version)


def model_name(version: str) -> str:
    """Plain-language name for a model version; unknown versions pass through."""
    return MODEL_NAMES.get(version, version)


def one_in(probability: float) -> str:
    """'1 in 37' for a 2.7% chance, '9 in 10' for 89%: easier to feel than a percentage."""
    if probability <= 0.0:
        return "never"
    if probability >= LIKELY:
        # "10 in 10" would read as a sure thing, so only a certainty may say it
        return f"{10 if probability >= 1.0 else min(9, round(probability * 10))} in 10"
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
    """Tapping a price adds it; tapping it again removes it. A player can be on a slip
    once per stat, so adding a second price for the same number replaces the first.
    `player_ids` maps each bet's position to its player-and-stat."""
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
    amount = round(amount, 2) + 0.0          # a loss under half a cent is $0.00, not -$0.00
    sign = "+" if signed and amount > 0 else "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def player_teams(games: pd.DataFrame) -> dict[int, str]:
    """Each player's most recent team, from the game logs."""
    latest = games.sort_values("game_date").groupby("player_id").tail(1)
    return {int(row.player_id): row.team for row in latest.itertuples()}


AVERAGE_COLUMNS = ("pts", "reb", "ast", "fg3m", "minutes")
# Measured on 2025-26 (scripts/nba_calibration_by_line.py): when the older models gave a bench
# player (under 18 minutes a game) a 70%+ chance, it came true about 70% of the time, not the
# 83% they said. So such "locks" are never suggested, though they can still be added by hand.
BENCH_MINUTES = 18.0
LOCK_CHANCE = 0.70
RECENT_GAMES = 10


def player_averages(games: pd.DataFrame) -> dict[int, dict[str, tuple[float, float]]]:
    """Each player's per-game average this season and over his last 10 games, for
    points, rebounds, assists and threes: {player_id: {"pts": (season, last10), ...}}.
    A player with no games this season gets the season he last played."""
    columns = [c for c in AVERAGE_COLUMNS if c in games.columns]
    newest = games.groupby("player_id")["season"].transform("max")
    season = games[games["season"] == newest].groupby("player_id")[columns].mean()
    recent = (games.sort_values("game_date").groupby("player_id").tail(RECENT_GAMES)
              .groupby("player_id")[columns].mean())
    return {int(pid): {col: (float(season.at[pid, col]), float(recent.at[pid, col]))
                       for col in columns} for pid in season.index}


def bench_players(averages: dict, max_minutes: float = BENCH_MINUTES) -> frozenset[int]:
    """Players averaging under `max_minutes` over their last 10 games."""
    return frozenset(pid for pid, stats in averages.items()
                     if "minutes" in stats and stats["minutes"][1] < max_minutes)


def average_text(averages: dict, player_id, column: str = "pts") -> str:
    """'avg 21.4 · last 10: 24.0', or empty when the player isn't in the logs."""
    pair = averages.get(int(player_id), {}).get(column)
    return "" if pair is None else f"avg {pair[0]:.1f} · last 10: {pair[1]:.1f}"


def sources(ledger: pd.DataFrame, game_date: str) -> dict[str, dict[str, list[str]]]:
    """What can be bet on a date: {book: {stat: [model versions that priced it]}}, from
    the ledger. Lets a screen offer only the choices that have prices."""
    day = ledger[ledger["game_date"] == game_date]
    found: dict[str, dict[str, list[str]]] = {}
    for (book, stat, version), _ in day.groupby(
            [day["book"].fillna(BOOK), day["stat"].fillna(STAT), "model_version"]):
        found.setdefault(book, {}).setdefault(stat, []).append(version)
    return found


def stat_column(stat: str) -> str:
    """The game-log column a stat's averages live in: 'rebounds' -> 'reb'."""
    return nba_stat_model.STATS[stat].column


def main_line(rows: pd.DataFrame) -> float | None:
    """The line to feature for one player when he has several (Kalshi lists many): the one
    whose over is closest to a coin flip, the lower line on a tie. None if he has no
    over/under legs. Other lines can still be reached, just not shown first."""
    overs = rows[rows["Side"] == "Over"]
    if overs.empty:
        return None
    chance = 1.0 / overs["Odds"].map(american_to_decimal)
    best = overs.assign(_distance=(chance - 0.5).abs()).sort_values(["_distance", "line"]).iloc[0]
    return float(best["line"])


def cents(american_odds: float) -> int:
    """A price as Kalshi shows it: the cost in cents of a contract that pays $1, which is
    also its implied chance. +100 is 50, -300 is 75, +300 is 25."""
    return round(100.0 / american_to_decimal(american_odds))


def ladder(rows: pd.DataFrame) -> list[dict]:
    """One player's lines as steps from low to high, like Kalshi's "20+  25+  30+":
    {"threshold", "yes", "no", "market", "model"}. `yes` is the candidate row to back
    "at least this many" and `no` the row to back the opposite (None for an X+ step,
    which has only the yes side). Over/under lines and X+ legs both make steps; when
    one number has both, the over/under line wins because it has both sides."""
    steps: dict[int, dict] = {}
    for _, group in rows[rows["Side"].isin(["Over", "Under"])].groupby("line"):
        overs, unders = group[group["Side"] == "Over"], group[group["Side"] == "Under"]
        if overs.empty:
            continue
        threshold = int(group["line"].iloc[0] // 1) + 1        # over 24.5 means 25+
        steps[threshold] = {
            "threshold": threshold, "yes": overs.index[0],
            "no": None if unders.empty else unders.index[0],
            "market": float(overs.iloc[0]["Market %"]), "model": float(overs.iloc[0]["Model %"])}
    for index, row in rows[rows["Side"].str.endswith("+")].iterrows():
        threshold = int(row["Side"][:-1])
        steps.setdefault(threshold, {
            "threshold": threshold, "yes": index, "no": None,
            "market": float(row["Market %"]), "model": float(row["Model %"])})
    return [steps[t] for t in sorted(steps)]


def default_step(steps: list[dict]) -> dict:
    """The step to show first: the one whose market chance is closest to a coin flip,
    the lower on a tie."""
    return min(steps, key=lambda s: (abs(s["market"] - 50.0), s["threshold"]))


def books_on(found: dict) -> list[str]:
    """The price sources that have lines, FanDuel first, then the rest alphabetically."""
    return sorted(found, key=lambda book: (book != BOOK, book))


def model_versions(found: dict, book: str) -> list[str]:
    """Every model version that priced anything for a source, newest name first."""
    return sorted({v for versions in found[book].values() for v in versions}, reverse=True)


def version_for(available: list[str], wanted: str) -> str:
    """The model to use for one stat: the one asked for if it priced that stat, else the
    simple baseline if it did, else the first listed. Only points have every model."""
    if wanted in available:
        return wanted
    return "ewma-v1" if "ewma-v1" in available else sorted(available)[0]


def all_candidates(ledger: pd.DataFrame, alt_ledger: pd.DataFrame, game_date: str,
                   model_version: str, book: str, found: dict,
                   minutes: dict[int, float] | None = None,
                   curves: dict | None = None) -> pd.DataFrame:
    """Every leg a source offers that day, across all stats, as one table (points first,
    then rebounds, assists, threes), so one slip can mix them. Each stat uses the chosen
    model when it priced that stat and the baseline when it didn't."""
    frames = [
        candidate_legs(ledger, alt_ledger, game_date,
                       version_for(found[book][stat], model_version), stat, book,
                       minutes, curves)
        for stat in nba_stat_model.STATS if stat in found.get(book, {})]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat(frames, ignore_index=True)


def candidate_legs(ledger: pd.DataFrame, alt_ledger: pd.DataFrame, game_date: str,
                   model_version: str, stat: str = STAT, book: str = BOOK,
                   minutes: dict[int, float] | None = None,
                   curves: dict | None = None) -> pd.DataFrame:
    """Every over, under and X+ leg one model priced on a date, for one stat and one
    price source. X+ legs exist only for FanDuel points.

    With `minutes` (each player's average over his last 10 games), a points leg's model chance
    is corrected for how often that model's chances came true for players in that role
    (models/nba_recalibration.py); `curves` replaces the saved corrections, for tests."""
    def model_over(row, chance: float) -> float:
        if minutes is None or stat != STAT:
            return float(chance)
        return nba_recalibration.calibrate(model_version, chance,
                                           minutes.get(int(row.player_id)), curves)

    rows = _over_under_rows(ledger, game_date, model_version, stat, book, model_over)
    if stat == STAT and book == BOOK:
        rows += _x_plus_rows(alt_ledger, game_date, model_version, model_over)
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    table = pd.DataFrame(rows)
    table["Blended %"] = table["prob"] * 100.0
    table["Leg EV %"] = [
        ev_per_unit(p, american_to_decimal(o)) * 100.0
        for p, o in zip(table["prob"], table["Odds"])]
    return table[COLUMNS].sort_values(["Game", "Player", "Leg"]).reset_index(drop=True)


def _over_under_rows(ledger: pd.DataFrame, game_date: str, model_version: str,
                     stat: str = STAT, book: str = BOOK, model_over=None) -> list[dict]:
    day = ledger[(ledger["game_date"] == game_date)
                 & (ledger["model_version"] == model_version)]
    # other books and stats share the ledger; each leg comes from exactly one of them
    for column, wanted in (("stat", stat), ("book", book)):
        if column in day.columns:
            day = day[day[column].fillna(DEFAULTS[column]) == wanted]
    noun = nba_stat_model.STATS[stat].label.lower()
    rows = []
    for row in day.itertuples():
        p_over = model_over(row, row.model_p_over) if model_over else row.model_p_over
        for is_over, odds, model_p, market_p in (
                (True, row.over_odds, p_over, row.fair_p_over),
                (False, row.under_odds, 1 - p_over, 1 - row.fair_p_over)):
            side = "Over" if is_over else "Under"
            rows.append(_leg_row(
                f"{row.player} · {side} {row.line} {noun}", row, side, odds, model_p,
                market_p, is_over, row.line, stat))
    return rows


def _x_plus_rows(alt_ledger: pd.DataFrame, game_date: str, model_version: str,
                 model_over=None) -> list[dict]:
    if alt_ledger.empty:
        return []
    day = alt_ledger[(alt_ledger["game_date"] == game_date)
                     & (alt_ledger["model_version"] == model_version)]
    return [
        _leg_row(f"{row.player} · {int(row.threshold)}+ {STAT}", row, f"{int(row.threshold)}+",
                 row.over_odds, model_over(row, row.model_p) if model_over else row.model_p,
                 row.market_p, True, row.threshold - 0.5, STAT)
        for row in day.itertuples()
    ]


def _leg_row(label, row, side, odds, model_p, market_p, is_over, line, stat) -> dict:
    blended = MODEL_WEIGHT * model_p + (1 - MODEL_WEIGHT) * market_p
    return {"Leg": label, "Stat": nba_stat_model.STATS[stat].label, "stat_key": stat,
            "Game": f"{row.away} @ {row.home}",
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
            american_odds=float(row.Odds), label=row.Leg, stat=row.stat_key)
        for row in chosen.itertuples()
    ]


# How much risk a suggested slip may carry, as the least chance it must have of
# hitting. A slip multiplies its legs' chances, so a few ordinary legs shrink fast.
STYLES = {"Safer": 0.35, "Balanced": 0.20, "Bigger payouts": 0.08}
DEFAULT_STYLE = "Balanced"
# A slip must also be worth the stake: the least it may win per $1 (so $10 on Safer wins
# at least $10), and it needs one real leg, not just locks, so locks only ever help.
MIN_PROFIT = {"Safer": 1.0, "Balanced": 2.0, "Bigger payouts": 6.0}
REAL_LEG_DECIMAL = 1.5          # about -200: the cheapest price that counts as a real leg


def suggest_parlays(candidates: pd.DataFrame, max_legs: int = 3, top: int = 5,
                    min_chance: float = STYLES[DEFAULT_STYLE], min_profit: float = 0.0,
                    real_leg_decimal: float | None = None,
                    one_per_game: bool = True,
                    bench: frozenset[int] = frozenset()) -> pd.DataFrame:
    """Best slips built from legs that are each worth betting on their own,
    at most one leg per game so the legs really are independent, keeping only
    slips that have at least `min_chance` of hitting and, when given, win at least
    `min_profit` per $1 and hold a leg paying `real_leg_decimal` or better (so a slip of
    only safe locks is never offered). Empty if fewer than two
    games have such a leg, or nothing clears the bar.

    Each game offers two legs to build from: the one with the best expected
    profit (usually a long shot) and the likeliest one that is still worth
    betting, so a cautious style has something sensible to work with.

    With `one_per_game` off (a single game was chosen), slips are built from different
    players in that game instead, one bet each, priced with the measured same-game
    correlations; the pool is each player's best leg and his likeliest worthwhile one."""
    good = _worthwhile_legs(candidates)
    if bench:                                      # bench players' "locks" are overrated
        overrated = good["player_id"].astype(int).isin(bench) & (
            good["Model %"] >= LOCK_CHANCE * 100.0)
        good = good[~overrated]
    key = "event_id" if one_per_game else "player_id"
    best_value = good.sort_values("Leg EV %", ascending=False).drop_duplicates(key)
    likeliest = good.sort_values("prob", ascending=False).drop_duplicates(key)
    pool = pd.concat([best_value, likeliest]).loc[lambda t: ~t.index.duplicated()]
    pool = pool.sort_values("Leg EV %", ascending=False).head(
        SUGGESTION_POOL if one_per_game else SAME_GAME_POOL)
    slips = []
    for size in range(2, max_legs + 1):
        for combo in combinations(pool.index, size):
            chosen = pool.loc[list(combo)]
            if one_per_game and chosen["event_id"].nunique() < size:
                continue                              # two legs from one game: not independent
            if chosen["player_id"].nunique() < size:
                continue                              # one player twice: a different bet
            decimals = chosen["Odds"].map(american_to_decimal)
            if decimals.prod() - 1.0 < min_profit:
                continue                              # wins too little to be worth the stake
            if real_leg_decimal is not None and not (decimals >= real_leg_decimal).any():
                continue
            if chosen["prob"].prod() < min_chance * PRUNE_BELOW:
                continue                              # cannot reach the bar, so skip the slow part
            summary = correlated.summarise(to_legs(chosen, {}), fast=True)
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
    best = pd.DataFrame(slips).sort_values("EV %", ascending=False).head(top).reset_index(drop=True)
    # the search ranked slips with the quick calculation; the ones shown get the exact one
    for position, bets in enumerate(best["bets"]):
        exact = correlated.summarise(to_legs(pool.loc[bets], {}))
        best.loc[position, ["Chance %", "Pays", "EV %"]] = [
            exact["joint_probability"] * 100.0, exact["decimal_odds"] - 1.0,
            exact["ev_per_unit"] * 100.0]
    return best


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
