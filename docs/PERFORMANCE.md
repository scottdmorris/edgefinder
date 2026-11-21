# Performance measurements

Measured locally on 2026-11-15. These are development measurements, not hosting
capacity estimates or guarantees for other machines.

## Browser loading

The Vite production build previously emitted one 339.48 KB JavaScript bundle
(99.71 KB gzip estimate). Screens now load separately:

- Shared app shell: 229.77 KB (72.39 KB gzip estimate).
- Parlay and its shared dependencies: another 38.76 KB (12.50 KB gzip estimate).
- Default Parlay opening: approximately 268.53 KB in total, about 21% less raw
  JavaScript than before (15% less using gzip estimates).
- Live, Players, Picks, Record and Last night load when selected. The logo and
  CSS are additional resources; gzip figures are build estimates, not evidence
  that the current server compresses responses.

The header and Live screen share one scoreboard request loop. It refreshes every
10 seconds on Live and every 60 seconds elsewhere, pauses in hidden tabs, and
preserves the last successful board when a refresh fails. Joining the shared
board does not trigger another request.

## API baseline

Run from the repository root using the development virtualenv:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_api.py --repeat 5
.\.venv\Scripts\python.exe scripts/benchmark_api.py --repeat 5 --profile /api/board
```

The benchmark uses FastAPI's in-process TestClient, real local ledgers and season
CSVs (including stale season caches), no upstream connections, and unavailable
injuries. Suggested offers are read through a read-only SQLite connection. It
only calls an allowlist of read routes and never requests new ideas. It clears
the service cache before each route, then makes five consecutive warm requests.
Cold does not mean an empty OS disk cache. Timings include API serialization but
exclude browser rendering, transport, upstream feed latency and concurrent users.

| Route | Cold ms | Warm median ms | Warm max ms | JSON bytes |
|---|---:|---:|---:|---:|
| /api/health | 2.4 | 1.0 | 1.1 | 134 |
| /api/days | 48.7 | 1.2 | 1.3 | 515 |
| /api/board | 3986.9 | 3800.9 | 4652.6 | 429465 |
| /api/picks | 81.7 | 34.1 | 34.8 | 36261 |
| /api/record | 1678.2 | 0.9 | 1.4 | 93943 |
| /api/players | 97.3 | 33.3 | 33.8 | 35313 |
| /api/teams | 73.6 | 7.0 | 8.0 | 4085 |
| /api/teams/BOS | 176.4 | 64.2 | 65.8 | 4815 |

A repeat run overlapping frontend validation was slower: board warm median
10,459.1 ms (max 22,176.6 ms), Picks 124.4 ms, Players 112.2 ms and the Boston
profile 162.8 ms. The completed benchmark also verified the read-only offer
connection. Machine load materially affects these results; compare future
changes with repeated, otherwise-idle runs against the same data snapshot.

The board is the demonstrated bottleneck. A separate cProfile run attributes
8.38 of 9.23 seconds to `suggestion_service.enrich`, across 418 candidate legs.
Profiling adds substantial overhead; these are not additional response-time
measurements. Repeated history assessment and sportsbook comparison filtering
dominate that work. Record is expensive cold, but its existing warm cache is
effective.

## Quote enrichment follow-up

On 2026-11-19, quote enrichment began building request-local lookups for ledger
rows, price snapshots and player histories. Each request still reads the current
snapshots and evaluates price age and tip time. Five warm requests per board and
version were measured locally with the same data and clock.

| Board | Warm board before | Warm board after | Warm enrichment before | Warm enrichment after |
|---|---:|---:|---:|---:|
| Nov 19 FanDuel, 102 legs | 1,586 ms | 1,535 ms | 1,100 ms | 989 ms |
| Nov 18 FanDuel, 196 legs | 2,999 ms | 2,222 ms | 2,527 ms | 1,728 ms |

Both timed API responses were byte-identical. A separate replay compared entire
enriched tables on the two slates for FanDuel, DraftKings and Kalshi, with four
clock settings per slate and book. All 24 batches (12,016 leg evaluations) matched
exactly, including the odds, blended and market probabilities, eligibility,
warnings and comparisons. These measurements exclude browser and network time.

The trial archive accepts the exact old and new enrichment fingerprints for this
verified transition. It retains the saved protocol and still checks every other
recipe file. No cache lifetime was added or increased.
