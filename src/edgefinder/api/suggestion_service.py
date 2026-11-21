"""Evidence attached to quotes, exact offered-slip recording, and a frozen nightly trial."""
import datetime as dt
import logging
import sqlite3
from collections.abc import Callable, Hashable
from functools import cache

import pandas as pd

from ..betting.odds_math import american_to_decimal, devig_two_way, implied_prob
from ..data import nba_props
from ..tracking import nba_paper, quote_evidence, suggested_record

log = logging.getLogger(__name__)
STYLE = "Higher hit rate"


def price_sources(book: str, fanduel: pd.DataFrame,
                  others: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """For a sportsbook source: its own refreshed prices, the other sportsbook's to compare
    with, and that book's name. Kalshi gets neither."""
    draftkings = others[others["book"] == "draftkings"] if "book" in others.columns else others
    if book == "fanduel":
        return fanduel, draftkings, "DraftKings"
    if book == "draftkings":
        return draftkings, fanduel, "FanDuel"
    return pd.DataFrame(), pd.DataFrame(), ""


def _group_lookup(frame: pd.DataFrame, *keys: str) -> Callable[[Hashable], pd.DataFrame]:
    """Look up a small slice without scanning the full table for each leg."""
    positions = frame.groupby(list(keys), sort=False).indices if not frame.empty else {}
    empty = frame.iloc[:0]

    @cache
    def lookup(key: Hashable) -> pd.DataFrame:
        rows = positions.get(key)
        return empty if rows is None else frame.take(rows)

    return lookup


def _snapshots_by_player(frame: pd.DataFrame) -> Callable[[Hashable], pd.DataFrame]:
    if not frame.empty:
        frame = frame.assign(event_id=frame.event_id.astype(str))
    return _group_lookup(frame, "event_id", "player")


def _recorded_quotes(frame: pd.DataFrame, chosen: dict, *, alternate: bool = False) -> dict:
    if frame.empty:
        return {}
    rows = frame[frame.model_version == chosen["model"]]
    if not alternate:
        rows = rows[rows.book == chosen["book"]]
    keys = ["event_id", "player_id", "threshold"] if alternate else ["event_id", "player_id", "stat", "line"]
    fields = [*keys, "commence_time", "recorded_at"]
    quotes = {}
    for event, player, *values in rows[fields].itertuples(index=False, name=None):
        *quote, tip, stamp = values
        # The original lookup used the first ledger row for duplicate keys.
        quotes.setdefault((str(event), player, *quote), (tip, stamp))
    return quotes


def enrich(table: pd.DataFrame, chosen: dict, ledger: pd.DataFrame, alt: pd.DataFrame,
           games: pd.DataFrame, now: dt.datetime) -> pd.DataFrame:
    out = table.copy()
    sportsbook = chosen["book"] in nba_paper.SPORTSBOOKS
    own, other, other_name = price_sources(
        chosen["book"], nba_props.load_snapshots() if sportsbook else pd.DataFrame(),
        nba_props.load_book_snapshots() if sportsbook else pd.DataFrame())
    own_by_player = _snapshots_by_player(own)
    other_by_player = _snapshots_by_player(other)
    history = _group_lookup(games, "player_id")
    main_quotes = _recorded_quotes(ledger, chosen)
    alt_quotes = _recorded_quotes(alt, chosen, alternate=True)
    now_stamp = pd.Timestamp(now)

    @cache
    def latest_own(key: tuple[str, str], tip: str) -> pd.Series | None:
        current = own_by_player(key)
        if current.empty:
            return None
        times = pd.to_datetime(current.fetched_at, utc=True, errors="coerce")
        current = current[(times <= now_stamp) & (times < pd.Timestamp(tip))]
        return None if current.empty else current.sort_values("fetched_at").iloc[-1]

    qualities, comparisons, tips = [], [], []
    for index, row in out.iterrows():
        alternate = str(row["Side"]).endswith("+")
        event, player_id = str(row["event_id"]), int(row["player_id"])
        player_key = event, row["Player"]
        if alternate:
            quote = alt_quotes.get((event, player_id, float(row["line"]) + .5))
        else:
            quote = main_quotes.get((event, player_id, row["stat_key"], row["line"]))
        tip, stamp = quote if quote is not None else (None, None)
        # Main sportsbook prices may have been refreshed since the model's early snapshot.
        changed_number = False
        incomplete_price = False
        if tip and not alternate and row["stat_key"] == "points":
            latest = latest_own(player_key, tip)
            if latest is not None:
                changed_number = float(latest.line) != float(row["line"])
                field = "under_odds" if row["Side"] == "Under" else "over_odds"
                if not changed_number and pd.notna(latest[field]):
                    if pd.notna(latest.over_odds) and pd.notna(latest.under_odds):
                        fair_over = devig_two_way(implied_prob(latest.over_odds), implied_prob(latest.under_odds))[0]
                        market = 1 - fair_over if row["Side"] == "Under" else fair_over
                        probability = (nba_paper.MODEL_WEIGHT * float(row["Model %"]) / 100
                                       + (1 - nba_paper.MODEL_WEIGHT) * market)
                        out.at[index, "Market %"] = market * 100
                        out.at[index, "prob"] = probability
                        out.at[index, "Blended %"] = probability * 100
                    else:
                        probability = float(row["prob"])
                        incomplete_price = True
                    out.at[index, "Odds"] = float(latest[field])
                    out.at[index, "Leg EV %"] = (probability * american_to_decimal(latest[field]) - 1) * 100
                    stamp = latest.fetched_at
        quality = quote_evidence.assess(row.to_dict() | {"date": chosen["date"]}, history(player_id), stamp, now)
        if incomplete_price:
            quality["warnings"].append("Two-sided market price unavailable")
            quality["eligible"] = False
        if changed_number:
            quality["warnings"].append("This number changed in the latest sportsbook snapshot")
            quality["eligible"] = False
        if not tip or pd.Timestamp(tip) <= pd.Timestamp(now):
            quality["warnings"].append("Game has started or its start time is unavailable")
            quality["eligible"] = False
        qualities.append(quality)
        comparisons.append(quote_evidence.comparisons(out.loc[index], other_by_player(player_key), now, tip, other_name)
                           if tip and not alternate else [])
        tips.append(tip)
    out["quality"], out["comparisons"], out["tip"] = qualities, comparisons, tips
    return out


def archive_idea(chosen: dict, style: str, game: str | None, table: pd.DataFrame,
                 ids: list[int], probability: float, payout: float, now: dt.datetime) -> str | None:
    selected = table.loc[ids]
    if "tip" not in selected or selected.tip.isna().any():
        return None
    legs = [{"quote_id": int(i), "player": r["Player"], "player_id": int(r["player_id"]),
             "game": r["Game"], "event_id": str(r["event_id"]), "tip": r["tip"],
             "stat": r["stat_key"], "side": r["Side"], "line": float(r["line"]),
             "odds": int(r["Odds"]),
             "evidence": {k: v for k, v in r.get("quality", {}).items() if k != "price_age_minutes"}} for i, r in selected.iterrows()]
    payload = {"day": chosen["date"], "book": chosen["book"], "model": chosen["model"],
               "style": style, "game": game, "legs": legs, "probability": probability,
               "payout": payout, "market_probability": 1 / payout,
               "payout_basis": "product of quoted single-leg prices; sportsbook SGP payout may differ"}
    trial: bool | str = (style == STYLE and not game and chosen["book"] == "fanduel"
                         and chosen["model"] == "context-v2" and len(legs) == 2)
    long_shot = suggested_record.LONG_SHOT_EXPERIMENT
    if (style == long_shot["style"] and not game and chosen["book"] == long_shot["book"]
            and chosen["model"] == long_shot["model"]):
        trial = long_shot["id"]
    try:
        return suggested_record.archive(payload, now, experiment=trial)
    except (OSError, ValueError, sqlite3.Error):
        log.exception("Could not record offered slip")
        return None


def capture_nightly() -> None:
    """Run after snapshots; do not backfill or select a winner after seeing results."""
    from . import service
    service.clear_cache()
    long_shot = suggested_record.LONG_SHOT_EXPERIMENT
    for name, book, model, style in (("higher-hit", "fanduel", "context-v2", STYLE),
                                     ("long-shot", long_shot["book"], long_shot["model"], long_shot["style"])):
        try:                                   # one trial failing never stops the other
            service.ideas(service.today().isoformat(), book, model, style)
        except (service.NotFound, ValueError):
            log.info("No qualifying %s trial slip available at this snapshot", name)
        except Exception:
            log.exception("Could not record the %s trial", name)
