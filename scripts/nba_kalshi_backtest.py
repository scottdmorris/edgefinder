"""Do the models beat Kalshi? A backtest on every settled 2025-26 player-points market.

For each market in Kalshi's archive (downloaded by kalshi_history_download.py):
- the price is Kalshi's own bid and ask in the last hour that closed 15+ minutes before tip-off
  (tip-off from NBA's official schedule);
- each model's chance comes from projections made walk-forward: trained on 2023-24 and 2024-25,
  never on 2025-26, and built only from games before the one being priced;
- the result is the market's settlement.

Then two questions, each with a 95% interval from resampling whole game nights (rungs on one
player's ladder, and players in one game, move together, so they are not independent bets):
1. **Accuracy.** Brier score (lower is better) of Kalshi's mid price, each model, and each model
   blended 30/70 with Kalshi, the way the app prices legs.
2. **Betting.** Every bet our recording rules would have made, bought at the ask with Kalshi's
   fee: the old Kalshi rule (2%+ expected value) and the current one (plus the guardrails).

Usage:  python scripts/nba_kalshi_backtest.py [--write docs/KALSHI_BACKTEST.md]
"""

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from edgefinder.betting import negbin  # noqa: E402
from edgefinder.data import kalshi_history as kh, nba_stats  # noqa: E402
from edgefinder.models import (  # noqa: E402
    nba_baselines, nba_context, nba_context_points, nba_context_v2, nba_features,
    nba_minutes_points, nba_points, nba_recalibration)
from edgefinder.models.nba_shot_features import add_shot_features  # noqa: E402
from edgefinder.tracking import nba_paper  # noqa: E402
from edgefinder.tracking.nba_player_lookup import plain_letters  # noqa: E402

import nba_context_eval as base  # noqa: E402
import nba_recalibration_fit as fit  # noqa: E402

DATA = ROOT / "data" / "kalshi_history"
SERIES = "KXNBAPTS"
TIP_TOLERANCE = dt.timedelta(minutes=10)
BOOTSTRAP = 2000
SEED = 7
# (version, short name, projection column, spread). Simple and Smarter use only what was known
# before the game; Smartest and Sharpest also use who sat out, read from who actually played,
# which includes late scratches the market could not have known: they are flagged in the report.
MODELS = [
    ("ewma-v1", "Simple", "pred_ewma", nba_points.MODEL_DISPERSION, True),
    ("minutes-v1", "Smarter", "pts_minutes_v1", nba_minutes_points.MODEL_DISPERSION, True),
    ("context-v1", "Smartest", "pts_context", nba_context_points.MODEL_DISPERSION, False),
    ("context-v2", "Sharpest", "pts_blend_shots", nba_context_v2.MODEL_DISPERSION, False),
]
WEIGHT = nba_paper.MODEL_WEIGHT
MIN_EV = nba_paper.MIN_EV_TO_RECORD
RECENT_GAMES = 20             # "consistent" is judged on a player's last 20 games
RATE_BANDS = [0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0]
LOCK_RATE, LOCK_PRICE, LOCK_LEGS = 0.9, 0.8, 3


# ---- the markets -----------------------------------------------------------------------------------

def name_key(name: str) -> str:
    """'Luka Dončić' and 'Luka Doncic', 'Jaren Jackson Jr.' and 'Jaren Jackson' match."""
    plain = plain_letters(name).lower().replace(".", "").replace("'", "")
    plain = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", plain)
    return re.sub(r"[^a-z]+", " ", plain).strip()


def schedule() -> pd.DataFrame:
    path = DATA / "schedule_2025_26.csv"
    if not path.exists():
        from nba_api.stats.endpoints import scheduleleaguev2
        frame = scheduleleaguev2.ScheduleLeagueV2(season="2025-26", timeout=60).get_data_frames()[0]
        frame[["gameId", "gameDateTimeUTC", "gameDateEst", "awayTeam_teamTricode",
               "homeTeam_teamTricode"]].to_csv(path, index=False)
    frame = pd.read_csv(path)
    return frame.assign(game_date=frame["gameDateEst"].str[:10],
                        tip=pd.to_datetime(frame["gameDateTimeUTC"], utc=True))


def load_markets() -> tuple[pd.DataFrame, dict]:
    """Settled markets with an official tip-off and a quote from before it."""
    counts = {}
    markets = json.loads((DATA / f"{SERIES}_markets.json").read_text(encoding="utf-8"))
    counts["archived"] = len(markets)
    rows = pd.DataFrame(kh.settled_rows(markets))
    counts["clean result"] = len(rows)

    tips = schedule().rename(columns={"awayTeam_teamTricode": "away",
                                      "homeTeam_teamTricode": "home", "tip": "official_tip"})
    rows = rows.merge(tips[["game_date", "away", "home", "official_tip"]],
                      on=["game_date", "away", "home"], how="inner")
    agree = (pd.to_datetime(rows["tip"], utc=True, format="ISO8601")
             - rows["official_tip"]).abs() <= TIP_TOLERANCE
    rows = rows[agree]
    counts["tip-off confirmed"] = len(rows)

    candles = {}
    with (DATA / f"{SERIES}_candles.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:      # a line still being written by the downloader
                continue
            candles[item["ticker"]] = item["candles"]
    quotes = [kh.pre_tip_quote(candles.get(t, []), tip.to_pydatetime())
              for t, tip in zip(rows["ticker"], rows["official_tip"])]
    rows = rows.assign(quote=quotes)
    rows = rows[rows["quote"].notna()]
    counts["quoted before tip"] = len(rows)
    rows = rows.assign(yes_bid=[q["yes_bid"] for q in rows["quote"]],
                       yes_ask=[q["yes_ask"] for q in rows["quote"]],
                       volume=[q["volume"] for q in rows["quote"]]).drop(columns="quote")
    rows["mid"] = (rows["yes_bid"] + rows["yes_ask"]) / 2.0
    rows["key"] = rows["player"].map(name_key)
    return rows, counts


# ---- the projections -------------------------------------------------------------------------------

def projections() -> tuple[pd.DataFrame, dict]:
    """2025-26 projections from models trained on the two seasons before, and role correction
    curves fitted on 2024-25 alone (the production curves were fitted on 2025-26, so using them
    here would test them on what they were fitted to). Both cached."""
    path, curves_path = DATA / "projections_2025_26.csv", DATA / "curves_2024_25.json"
    if path.exists() and curves_path.exists():
        return pd.read_csv(path), json.loads(curves_path.read_text(encoding="utf-8"))
    today = dt.date.today()
    games = pd.concat([nba_stats.load_season(s, today=today) for s in base.SEASONS],
                      ignore_index=True)
    features = add_shot_features(nba_context.add_context(nba_features.build_features(games), games))
    baseline = nba_baselines.add_baseline_predictions(games, "pts")[
        ["player_id", "game_id", "pred_ewma"]]
    features = features.merge(baseline, on=["player_id", "game_id"], how="left")
    features["recent_minutes"] = fit.recent_minutes(features)

    validation = fit.scored(features, base.SELECT_TRAIN, base.VALIDATE)
    curves = {version: fit.fit_curves(fit.long_table(validation, column, width))
              for version, (column, width) in fit.MODELS.items()}
    curves_path.write_text(json.dumps(curves), encoding="utf-8")

    scored = fit.scored(features, base.FINAL_TRAIN, base.TEST)
    names = games.drop_duplicates("player_id").set_index("player_id")["player_name"]
    keep = ["player_id", "game_id", "game_date", "team", "pts", "recent_minutes"] +         [m[2] for m in MODELS]
    out = scored[keep].assign(player_name=scored["player_id"].map(names))
    out["game_date"] = pd.to_datetime(out["game_date"]).dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)
    return out, curves


def join(markets: pd.DataFrame, projected: pd.DataFrame, curves: dict,
         counts: dict) -> pd.DataFrame:
    projected = projected.assign(key=projected["player_name"].map(name_key))
    # a name shared by two players on one date can't be matched safely: drop it
    unique = projected.groupby(["game_date", "key"]).filter(lambda g: len(g) == 1)
    joined = markets.merge(unique, on=["game_date", "key"], how="inner")
    counts["matched to a projection"] = len(joined)
    # the market settled on the same points the game log shows
    joined = joined[(joined["pts"] >= joined["threshold"]) == (joined["hit"] == 1)]
    counts["result agrees with box score"] = len(joined)
    roles = [nba_recalibration.role_for(m) for m in joined["recent_minutes"]]
    for version, short, column, width, _ in MODELS:
        raw = negbin.over_prob(joined["threshold"] - 0.5, joined[column].to_numpy(), width)
        joined[f"p_{short}"] = raw
        model_curves = curves.get(version, {})
        joined[f"p_{short} corrected"] = [
            float(np.interp(c, model_curves[r]["x"], model_curves[r]["y"]))
            if r in model_curves else float(c) for c, r in zip(raw, roles)]
    return joined.reset_index(drop=True)


# ---- scoring ---------------------------------------------------------------------------------------

def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def by_night(frame: pd.DataFrame) -> list[np.ndarray]:
    return [idx.to_numpy() for _, idx in frame.groupby("game_date").groups.items()]


def interval(frame: pd.DataFrame, stat, rng) -> tuple[float, float, float]:
    """The statistic and a 95% interval from resampling whole game nights."""
    nights = by_night(frame)
    point = stat(frame.index.to_numpy())
    draws = []
    for _ in range(BOOTSTRAP):
        pick = rng.integers(0, len(nights), len(nights))
        draws.append(stat(np.concatenate([nights[i] for i in pick])))
    low, high = np.percentile(draws, [2.5, 97.5])
    return point, float(low), float(high)


def accuracy(frame: pd.DataFrame, rng) -> pd.DataFrame:
    y, market = frame["hit"].to_numpy(float), frame["mid"].to_numpy()
    rows = [{"Prices from": "Kalshi (mid price)", "Brier": brier(market, y),
             "vs Kalshi": "", "95% interval": ""}]
    for _, short, _, _, clean in MODELS:
        raw, fixed = frame[f"p_{short}"].to_numpy(), frame[f"p_{short} corrected"].to_numpy()
        for label, chance in ((short, raw), (f"{short}, corrected", fixed),
                              (f"{short} 30/70 with Kalshi", WEIGHT * raw + (1 - WEIGHT) * market),
                              (f"{short}, corrected, 30/70 with Kalshi",
                               WEIGHT * fixed + (1 - WEIGHT) * market)):
            diff = lambda idx, c=chance: brier(c[idx], y[idx]) - brier(market[idx], y[idx])  # noqa: E731
            point, low, high = interval(frame, diff, rng)
            rows.append({"Prices from": label + ("" if clean else " *"), "Brier": brier(chance, y),
                         "vs Kalshi": f"{point:+.4f}", "95% interval": f"{low:+.4f} to {high:+.4f}"})
    return pd.DataFrame(rows)


def bets(frame: pd.DataFrame, short: str, guarded: bool) -> pd.DataFrame:
    """Every bet the recording rule makes with this model: the better side by blended EV at the
    ask, after Kalshi's fee, if it clears 2% (and, if guarded, the model guardrails)."""
    p_model = frame[f"p_{short}"].to_numpy()
    market = frame["mid"].to_numpy()
    blend = WEIGHT * p_model + (1 - WEIGHT) * market
    yes_price, no_price = frame["yes_ask"].to_numpy(), 1.0 - frame["yes_bid"].to_numpy()

    # per unit staked: buy 1/price contracts and pay the fee on each; a win returns 1 a contract
    def per_unit(chance, price):
        fee = kh.taker_fee(price) / price
        return chance / price - 1.0 - fee
    ev_yes, ev_no = per_unit(blend, yes_price), per_unit(1 - blend, no_price)
    side_yes = ev_yes >= ev_no
    edge = np.where(side_yes, ev_yes, ev_no)
    price = np.where(side_yes, yes_price, no_price)
    model_side = np.where(side_yes, p_model, 1 - p_model)
    market_side = np.where(side_yes, market, 1 - market)
    take = edge >= MIN_EV
    if guarded:
        take &= (model_side >= nba_paper.MIN_MODEL_P) & \
            (np.abs(model_side - market_side) <= nba_paper.MAX_DISAGREEMENT)
    won = np.where(side_yes, frame["hit"].to_numpy() == 1, frame["hit"].to_numpy() == 0)
    fee = kh.taker_fee(price) / price
    units = np.where(won, 1.0 / price - 1.0 - fee, -1.0 - fee)
    out = frame.assign(side=np.where(side_yes, "yes", "no"), price=price, edge=edge,
                       won=won, units=units)
    return out[take]


def betting(frame: pd.DataFrame, rng) -> pd.DataFrame:
    rows = []
    variants = [(short, clean) for _, short, _, _, clean in MODELS] +         [(f"{short} corrected", clean) for _, short, _, _, clean in MODELS]
    for short, clean in variants:
        for rule, guarded in (("2%+ value only", False), ("with guardrails", True)):
            placed = bets(frame, short, guarded)
            if placed.empty:
                continue
            placed = placed.reset_index(drop=True)
            units = placed["units"].to_numpy()
            roi = lambda idx: float(units[idx].mean()) if len(idx) else 0.0  # noqa: E731
            point, low, high = interval(placed, roi, rng)
            rows.append({"Model": short + ("" if clean else " *"), "Rule": rule,
                         "Bets": len(placed), "Won": f"{placed['won'].mean():.1%}",
                         "Typical price": f"{placed['price'].median():.2f}",
                         "Units": f"{units.sum():+.1f}", "Return": f"{point:+.1%}",
                         "95% interval": f"{low:+.1%} to {high:+.1%}"})
    return pd.DataFrame(rows)


def calibration(frame: pd.DataFrame) -> pd.DataFrame:
    bands = pd.cut(frame["mid"], np.arange(0, 1.0001, 0.1), include_lowest=True)
    out = frame.groupby(bands, observed=True).agg(
        markets=("hit", "size"), kalshi_said=("mid", "mean"), happened=("hit", "mean"),
        simple_said=("p_Simple", "mean"), simple_corrected=("p_Simple corrected", "mean"),
        smarter_said=("p_Smarter", "mean"), smarter_corrected=("p_Smarter corrected", "mean"))
    out.index = out.index.astype(str)
    return (out * [1, 100, 100, 100, 100, 100, 100]).round(1)


def by_price(frame: pd.DataFrame, short: str) -> pd.DataFrame:
    placed = bets(frame, short, False)
    buckets = pd.cut(placed["price"], [0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0])
    out = placed.groupby(buckets, observed=True).agg(
        bets=("units", "size"), won=("won", "mean"), units=("units", "sum"),
        roi=("units", "mean"))
    out.index = out.index.astype(str)
    return out.assign(won=(out["won"] * 100).round(1), units=out["units"].round(1),
                      roi=(out["roi"] * 100).round(1))


# ---- did the edge last? ----------------------------------------------------------------------------

def split_night(frame: pd.DataFrame) -> str:
    """The middle game night: the season is cut there into an early and a late half."""
    nights = sorted(frame["game_date"].unique())
    return nights[len(nights) // 2]


def halves(frame: pd.DataFrame, rng) -> pd.DataFrame:
    """Kalshi's Brier score and each 30/70 blend's gap to it, on each half of the season."""
    cut = split_night(frame)
    parts = ((f"Before {cut}", frame[frame["game_date"] < cut]),
             (f"From {cut}", frame[frame["game_date"] >= cut]))
    rows = []
    for label, part in parts:
        part = part.reset_index(drop=True)
        y, market = part["hit"].to_numpy(float), part["mid"].to_numpy()
        row = {"Nights": label, "Markets": len(part), "Kalshi Brier": brier(market, y)}
        for _, short, _, _, clean in MODELS:
            chance = WEIGHT * part[f"p_{short}"].to_numpy() + (1 - WEIGHT) * market
            diff = lambda idx, c=chance: brier(c[idx], y[idx]) - brier(market[idx], y[idx])  # noqa: E731
            point, low, high = interval(part, diff, rng)
            row[short + ("" if clean else " *")] = f"{point:+.4f} ({low:+.4f} to {high:+.4f})"
        rows.append(row)
    return pd.DataFrame(rows)


# ---- are consistent players easy locks? ------------------------------------------------------------

def recent_rates(frame: pd.DataFrame, games: pd.DataFrame) -> pd.Series:
    """For each market, the share of the player's previous RECENT_GAMES games (this season or
    last) in which he reached the market's number. Only games before the one being priced count.
    NaN when he has fewer than RECENT_GAMES behind him."""
    games = games.sort_values(["player_id", "game_date"])
    rates = []
    for number in sorted(frame["threshold"].unique()):
        reached = (games["pts"] >= number).astype(float)
        rate = reached.groupby(games["player_id"]).transform(
            lambda s: s.shift().rolling(RECENT_GAMES, min_periods=RECENT_GAMES).mean())
        rates.append(games[["player_id", "game_id"]].assign(threshold=number, recent_rate=rate))
    merged = frame[["player_id", "game_id", "threshold"]].merge(
        pd.concat(rates), on=["player_id", "game_id", "threshold"], how="left")
    return pd.Series(merged["recent_rate"].to_numpy(), index=frame.index)


def yes_units(frame: pd.DataFrame) -> np.ndarray:
    """Profit per unit from buying Yes at the ask, after Kalshi's fee."""
    price = frame["yes_ask"].to_numpy()
    fee = kh.taker_fee(price) / price
    return np.where(frame["hit"].to_numpy() == 1, 1.0 / price - 1.0 - fee, -1.0 - fee)


def consistent(frame: pd.DataFrame, rng) -> pd.DataFrame:
    """Buying Yes on every market, grouped by how often the player reached that number lately."""
    rated = frame.dropna(subset=["recent_rate"])
    bands = pd.cut(rated["recent_rate"], RATE_BANDS, include_lowest=True)
    rows = []
    for band, part in rated.groupby(bands, observed=True):
        part = part.reset_index(drop=True)
        units = yes_units(part)
        point, low, high = interval(part, lambda idx: float(units[idx].mean()), rng)
        rows.append({f"Reached it in his last {RECENT_GAMES}": f"{band.left:.0%} to {band.right:.0%}"
                     if band.left > 0 else f"up to {band.right:.0%}",
                     "Markets": len(part), "Kalshi's ask": f"{part['yes_ask'].mean():.1%}",
                     "Happened": f"{part['hit'].mean():.1%}", "Return buying Yes": f"{point:+.1%}",
                     "95% interval": f"{low:+.1%} to {high:+.1%}"})
    return pd.DataFrame(rows)


def lock_slips(frame: pd.DataFrame, rng) -> dict:
    """One three-leg slip a night from the steadiest favourites: the three markets with the
    highest recent rate (LOCK_RATE or more, priced LOCK_PRICE or more), one per player, bought
    at the ask as independent legs."""
    locks = frame[(frame["recent_rate"] >= LOCK_RATE) & (frame["mid"] >= LOCK_PRICE)]
    units, wins, costs = [], [], []
    for _, night in locks.sort_values(["recent_rate", "mid"], ascending=False).groupby("game_date"):
        legs = night.drop_duplicates("player_id").head(LOCK_LEGS)
        if len(legs) < LOCK_LEGS:
            continue
        ask = legs["yes_ask"].to_numpy()
        cost, won = float(np.prod(ask)), bool((legs["hit"] == 1).all())
        fees = float(np.sum(kh.taker_fee(ask) / ask))
        units.append((1.0 / cost - 1.0 if won else -1.0) - fees)
        wins.append(won)
        costs.append(cost)
    units = np.array(units)
    draws = [units[rng.integers(0, len(units), len(units))].mean() for _ in range(BOOTSTRAP)]
    low, high = np.percentile(draws, [2.5, 97.5])
    return {"nights": len(units), "cost": float(np.mean(costs)), "won": float(np.mean(wins)),
            "roi": float(units.mean()), "low": float(low), "high": float(high)}


# ---- report ----------------------------------------------------------------------------------------

def md(frame: pd.DataFrame, index: bool = False, digits: int = 4) -> str:
    """A markdown table, without needing tabulate."""
    table = frame.reset_index() if index else frame
    def cell(value):
        return f"{value:.{digits}f}" if isinstance(value, float) else str(value)
    head = "| " + " | ".join(map(str, table.columns)) + " |"
    rule = "|" + "|".join("---" for _ in table.columns) + "|"
    body = ["| " + " | ".join(cell(v) for v in row) + " |" for row in table.itertuples(index=False)]
    return "\n".join([head, rule, *body])


def lock_text(slips: dict) -> str:
    return (f"**A nightly {LOCK_LEGS}-leg slip of the steadiest favourites** (reached the number "
            f"in {LOCK_RATE:.0%}+ of the last {RECENT_GAMES} games, priced {LOCK_PRICE:.0%}+, one "
            f"leg a player): {slips['nights']} nights, average cost {slips['cost']:.2f}, won "
            f"{slips['won']:.1%}, return {slips['roi']:+.1%} (95% interval {slips['low']:+.1%} to "
            f"{slips['high']:+.1%}). The legs are priced as independent, which is how Kalshi "
            "would sell them one by one.")


def report(frame: pd.DataFrame, counts: dict, rng) -> str:
    nights, players = frame["game_date"].nunique(), frame["player_id"].nunique()
    lines = ["# Kalshi backtest, 2025-26", "",
             f"Generated {dt.date.today():%b %d, %Y} by `scripts/nba_kalshi_backtest.py`.", "",
             f"**{len(frame):,} settled player-points markets** on {nights} game nights and "
             f"{players} players, each priced by Kalshi before tip-off and by every model.", "",
             "## What was kept", "", "| Step | Markets |", "|---|---:|"]
    lines += [f"| {step} | {n:,} |" for step, n in counts.items()]
    lines += ["", "Only rotation players (20+ minutes a game before the game) have projections, "
              "and a market needs a two-sided quote in the hour before tip-off.", "",
              "## 1. Who is more accurate?", "",
              "\"Corrected\" applies the role correction curves (bench, rotation, starter) "
              "fitted on 2024-25 only, so this season is new to them too.", "",
              "Brier score: the average squared gap between the chance given and what happened "
              "(lower is better). A negative \"vs Kalshi\" means more accurate than Kalshi's own "
              "price. The interval resamples whole game nights.", "",
              md(accuracy(frame, rng)), "",
              "\\* Uses who sat out, read from who actually played. That includes late scratches "
              "the market could not have priced, so it flatters these models here.", "",
              "## 2. Would the recording rules have made money?", "",
              "Every bet the rule picks, 1 unit each, bought at Kalshi's ask (or 1 minus the "
              "bid for No) and paying Kalshi's taker fee. \"Return\" is profit per unit staked.", "",
              md(betting(frame, rng)), "",
              "### Simple model, by the price paid (2%+ value only)", "",
              md(by_price(frame, "Simple"), index=True, digits=1), "",
              "### The same, with the role correction", "",
              md(by_price(frame, "Simple corrected"), index=True, digits=1), "",
              "## 3. Is Kalshi's price honest?", "",
              "Markets grouped by Kalshi's mid price before tip-off (all numbers in %).", "",
              md(calibration(frame), index=True, digits=1), "",
              "## 4. Did the models' edge last?", "",
              "The season cut at its middle game night. Each model column is the 30/70 blend's "
              "Brier score minus Kalshi's (negative is better than Kalshi), with its interval.", "",
              md(halves(frame, rng)), "",
              "Player-points markets were new on Kalshi early in the season. If the blend only "
              "beats Kalshi in the early half, the models were ahead of a young market, not of "
              "the market as it prices now.", "",
              "## 5. Are consistent players easy locks?", "",
              f"Every market, grouped by how often the player reached that number in his last "
              f"{RECENT_GAMES} games before this one, and what buying Yes at the ask returned.", "",
              md(consistent(frame, rng)), "",
              lock_text(lock_slips(frame, rng)), "",
              "## Limits", "",
              "- One season. The models never saw it, but the rules and spreads were chosen with "
              "earlier seasons, and this test was run once after the fact.",
              "- Prices are the last hourly quote at least 15 minutes before tip-off; a real bet "
              "an hour or more earlier would have got a different price, and a big order would "
              "move it.",
              "- Fees are Kalshi's taker formula (7% x price x (1 - price) per contract) without "
              "rounding up to the cent, which costs a little more on small orders.",
              "- Bets on one player's ladder, and players in one game, are not independent; the "
              "intervals account for that by resampling whole nights, but they are still "
              "approximate.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path, default=None)
    args = parser.parse_args()
    rng = np.random.default_rng(SEED)
    markets, counts = load_markets()
    projected, curves = projections()
    frame = join(markets, projected, curves, counts)
    games = pd.concat([nba_stats.load_season(s, today=dt.date.today()) for s in base.SEASONS],
                      ignore_index=True)
    frame["recent_rate"] = recent_rates(frame, games)
    frame.to_csv(DATA / "backtest_rows.csv", index=False)
    text = report(frame, counts, rng)
    print(text)
    if args.write:
        args.write.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
