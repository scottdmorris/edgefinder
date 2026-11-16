"""Measure local API processing and serialization, without network or ledger writes.

Usage: python scripts/benchmark_api.py --repeat 5 (use the project's virtualenv)
Optional: --profile /api/board to print the slowest cumulative Python calls.

Cold means an empty service cache, not a fresh OS disk cache. Warm requests reuse
that cache. This in-process benchmark excludes transport and upstream feed latency.
Season data comes from local CSVs even if stale; injuries are explicitly unavailable.
Only the read-only routes below are supported, so profiling never offers new slips.
"""

import argparse
import cProfile
import io
import pstats
import socket
import sqlite3
import statistics
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from edgefinder.api import service  # noqa: E402
from edgefinder.api.app import app  # noqa: E402
from edgefinder.data import nba_injuries, nba_stats  # noqa: E402
from edgefinder.tracking import suggested_record  # noqa: E402

ROUTES = ("/api/health", "/api/days", "/api/board", "/api/picks", "/api/record",
          "/api/players", "/api/teams", "/api/teams/BOS")


def _local_season(season: str, **_: object):
    path = nba_stats.NBA_DIR / f"games_{season}.csv"
    if not path.is_file():
        raise nba_stats.NbaDataError(f"Local season cache is missing: {season}")
    return nba_stats._read(path)


def _no_network(*_: object, **__: object) -> None:
    raise OSError("Outbound network is disabled during benchmarking")


def _no_injuries():
    raise nba_injuries.InjuryDataError("Injuries unavailable in offline benchmark")


@contextmanager
def _read_offers(path: Path | None = None):
    source = (path or suggested_record.DB_PATH).resolve()
    db = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    try:
        yield db
    finally:
        db.close()


def measure(client: TestClient, route: str, repeat: int) -> dict:
    service.clear_cache()
    started = perf_counter()
    response = client.get(route)
    cold_ms = (perf_counter() - started) * 1000
    response.raise_for_status()
    samples = []
    for _ in range(repeat):
        started = perf_counter()
        response = client.get(route)
        samples.append((perf_counter() - started) * 1000)
        response.raise_for_status()
    return {"route": route, "cold_ms": cold_ms, "median_ms": statistics.median(samples),
            "max_ms": max(samples), "bytes": len(response.content)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--profile", choices=ROUTES)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    with ExitStack() as stack:
        # Start the event loop before blocking sockets: Windows uses a local
        # socketpair internally to wake its asyncio loop.
        client = stack.enter_context(TestClient(app))
        stack.enter_context(patch.object(socket.socket, "connect", _no_network))
        stack.enter_context(patch.object(socket.socket, "connect_ex", _no_network))
        stack.enter_context(patch.object(nba_stats, "load_season", _local_season))
        stack.enter_context(patch.object(nba_injuries, "fetch_injuries", _no_injuries))
        stack.enter_context(patch.object(suggested_record, "connect", _read_offers))
        print("Local CSVs, offline injuries; no upstream or transport latency.")
        print(f"Warm samples per route: {args.repeat}. Cold: cleared service cache.")
        print("| Route | Cold ms | Warm median ms | Warm max ms | JSON bytes |")
        print("|---|---:|---:|---:|---:|")
        for route in ROUTES:
            result = measure(client, route, args.repeat)
            print(f"| {route} | {result['cold_ms']:.1f} | {result['median_ms']:.1f} | "
                  f"{result['max_ms']:.1f} | {result['bytes']} |")
        if args.profile:
            # Warm the route, then profile its handler directly: cProfile around
            # TestClient would miss the work performed in its worker thread.
            from edgefinder.api import picks, players, record, teams
            handlers = {"/api/health": service.health, "/api/days": service.days,
                        "/api/board": service.board, "/api/picks": picks.picks,
                        "/api/record": record.record, "/api/players": players.players,
                        "/api/teams": teams.options,
                        "/api/teams/BOS": lambda: teams.profile("BOS")}
            handlers[args.profile]()
            profiler = cProfile.Profile()
            profiler.runcall(handlers[args.profile])
            output = io.StringIO()
            pstats.Stats(profiler, stream=output).strip_dirs().sort_stats("cumulative").print_stats(15)
            print(output.getvalue())
    service.clear_cache()


if __name__ == "__main__":
    main()
