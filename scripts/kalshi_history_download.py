"""Download Kalshi's archive of settled NBA player-points markets and each one's price history.

Free and keyless, but one request per market's history, so it is cached and resumable: run it
again and it only fetches what is missing. Everything goes under data/kalshi_history/ (git-ignored).

Usage:  python scripts/kalshi_history_download.py [--series KXNBAPTS] [--limit N]
"""

import argparse
import datetime as dt
import threading
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from edgefinder.data import kalshi, kalshi_history as kh  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "kalshi_history"
WORKERS = 5                   # with each request taking ~0.35s, about 14 a second: inside
                              # Kalshi's public limit of 20 reads a second
HISTORY_HOURS = 48            # price history kept per market: the two days before tip-off
RETRIES = 5


def get(path: str, params: dict) -> dict:
    for attempt in range(RETRIES):
        try:
            response = requests.get(f"{kalshi.BASE}{path}", params=params,
                                    timeout=kalshi.REQUEST_TIMEOUT)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        return response.json()
    raise kalshi.KalshiDataError(f"gave up on {path} after {RETRIES} tries")


def markets(series: str) -> list[dict]:
    path = OUT / f"{series}_markets.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    found = kh.fetch_markets(series, get)
    path.write_text(json.dumps(found), encoding="utf-8")
    return found


def repair(path: Path) -> None:
    """Cut off a last line left half-written when a run was stopped, so the next one is not
    glued onto it."""
    if not path.exists():
        return
    data = path.read_bytes()
    end = data.rfind(b"\n") + 1
    if end < len(data):
        path.write_bytes(data[:end])


def done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    tickers = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                tickers.add(json.loads(line)["ticker"])
            except (json.JSONDecodeError, KeyError):
                continue
    return tickers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--series", default="KXNBAPTS")
    parser.add_argument("--limit", type=int, default=None, help="stop after this many markets")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    rows = kh.settled_rows(markets(args.series))
    candles_file = OUT / f"{args.series}_candles.jsonl"
    repair(candles_file)
    have = done(candles_file)
    todo = [r for r in rows if r["ticker"] not in have and r["total_volume"] > 0]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(rows):,} settled markets; {len(have):,} histories cached; fetching {len(todo):,}",
          flush=True)

    lock, written = threading.Lock(), [0]
    with candles_file.open("a", encoding="utf-8") as out:
        def fetch(row: dict) -> None:
            tip = dt.datetime.fromisoformat(row["tip"])
            params = {"start_ts": int((tip - dt.timedelta(hours=HISTORY_HOURS)).timestamp()),
                      "end_ts": int(tip.timestamp()), "period_interval": 60}
            try:
                candles = get(kh.candles_path(row["ticker"]), params).get("candlesticks") or []
            except (requests.HTTPError, kalshi.KalshiDataError) as error:
                print(f"skip {row['ticker']}: {error}", flush=True)
                return
            with lock:                       # one whole line at a time, flushed as it goes
                out.write(json.dumps({"ticker": row["ticker"], "candles": candles}) + "\n")
                out.flush()
                written[0] += 1
                if written[0] % 1000 == 0:
                    print(f"{written[0]:,} / {len(todo):,}", flush=True)

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            list(pool.map(fetch, todo))
    print(f"done: {written[0]:,} fetched", flush=True)


if __name__ == "__main__":
    main()
