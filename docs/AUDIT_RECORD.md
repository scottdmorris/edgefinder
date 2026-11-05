# Track-record audit

Reviewed at commit `d41dc6c` (`main`). Read-only review: no code was changed. Findings marked
**reproduced** were run against that commit's code in a scratch directory (the script is in the
appendix); the others are read from the code.

## Summary

The record's one promise, "every pick is written down before the game and only the result is
filled in afterwards", is **measured but not enforced**. The Record tab counts picks recorded after
tip-off, which is honest, but nothing stops one from being written, and a pick recorded after
tip-off still counts in the record, the units and the running-profit chart. The ledger is a
plain CSV that is git-ignored, rewritten in full by the settle job, timestamped by the machine's
own clock, and can be edited by hand with no trace, so the record asks a stranger to trust the
operator, which is the thing it says it does not do. Grading rules for voids are simple and mostly
sound, but pushes are avoided by dropping whole-number lines, and postponed games and scratches
are indistinguishable. Nothing hides losing rows today, but nothing prevents it either. The
numbers on the Record tab appear to match the ledger arithmetically (read from the code, not re-run). Before this is public it needs a
tamper-evident log, an enforced pre-tip rule, and a legal and licensing review.

---

## Findings, most severe first

### 1. The ledger can be edited or backfilled with no trace — HIGH

- **Where:** `src/edgefinder/tracking/nba_paper.py:122-126` (`save_ledger` overwrites the whole
  file), `:128-152` (`append_rows`), `.gitignore` (the ledger CSVs are ignored, so there is no
  history), `scripts/nba_props_settle.py:30` and `:54`.
- **Issue:** the ledger is `data/nba_paper_log.csv`. Anyone with file access can change `result`,
  `pnl_units`, `pick_side`, `recorded_at` or delete rows, and the Record tab will show the new
  numbers. The tab's "Picks locked / Every pick was recorded before its game started" is computed
  from the same file, so it is edited along with it. There is no backup, no version history and no
  external witness.
- **Reproduction (reproduced):** settle a losing pick, then
  `raw.loc[raw.result=="loss", ["result","pnl_units"]] = ["win", 0.909091]; raw.to_csv(path)`.
  Record goes from `0-1, -1.00 units` to `1-0, +0.91 units`; `integrity()` is unchanged and reports
  nothing wrong.
- **Fix:** see "A tamper-evident log" below. Minimum: stop ignoring the ledger in git or ship it to
  an append-only store, and publish a daily digest (SHA-256 of the file) somewhere the operator
  cannot rewrite.

### 2. A pick recorded after tip-off is accepted and still counts — HIGH

- **Where:** `nba_paper.py:51-` (`build_ledger_rows` takes `recorded_at` as a free argument and
  never compares it with `commence_time`); `nba_record.py:55-66` (`integrity` counts such picks
  but nothing excludes them); `nba_record.py:77-79` and `:98-105` (`graded`, `cumulative_units`
  use every pick); `nba_paper.py:258-` (`summary`); `ui/nba_record_tab.py:25-31,46`.
- **Issue:** the tab says "Some picks were recorded after tip-off: **ignore those**", but the
  record, units, return, running-profit chart and day-by-day table all include them. So the page
  reports a clean-looking tile and a profit figure that mixes pre- and post-tip picks. The
  backfill path (`scripts/nba_props_snapshot.py:177-188`) does check `tip_time(event) <= now`, but
  that is a convention in one script, not a rule in the ledger.
- **Reproduction (reproduced):** `build_ledger_rows(ev, lines, pred, "2026-11-04T01:00:00+00:00", ...)`
  for an event whose `commence_time` is `2026-11-04T00:00:00+00:00` returns a pick, `append_rows`
  writes it (returns 1), `integrity()["after_tip"] == 1`, and `cumulative_units(...)` still
  contains its units.
- **Fix:** reject in `append_rows` (and `build_ledger_rows`) any row with
  `recorded_at >= commence_time`; or mark it `late=True` and make `summary`, `locked_picks`
  (hence the log, daily table and profit chart) and `calibration_*` exclude late rows. Show the late
  count as a separate figure.

### 3. The timestamp is the operator's own clock — HIGH

- **Where:** `scripts/nba_props_snapshot.py:130`, `:151`, `:171`
  (`recorded_at=dt.datetime.now(dt.timezone.utc).isoformat()`); `commence_time` comes from the
  Odds API event list.
- **Issue:** "locked X minutes before tip" is the difference between a locally-generated string and
  an API field. The local clock can be wrong or changed, and the string is written by the same
  process that writes the pick. Nothing outside the operator vouches for the time. The odds
  themselves (`over_odds`, `under_odds`) are also only the operator's copy of what the sportsbook
  showed.
- **Fix:** anchor the time externally: publish a digest (finding 1) or use an RFC 3161 timestamp
  authority / transparency log, so "this exact file existed at this time" is provable by a third
  party. Store the raw API response (or its hash) with each snapshot (`nba_props.append_snapshot`
  already archives lines; include it in the digest).

### 4. Pushes are avoided by dropping lines; the grading rules are undocumented — MEDIUM

- **Where:** `nba_paper.py:75-76` and `nba_alt.py` (`float(point).is_integer()` rows are skipped),
  `nba_paper.py:201` (`went_over = actual > line`), `nba_alt.py` (`won = actual >= threshold`).
- **Issue:** no push can occur in the main ledger because whole-number lines are never recorded.
  That is a reasonable simplification, but it is a silent filter on which lines are in the record
  (survivorship, finding 8) and is mentioned only in a docstring, not on the Record page. A book
  that posts 24 instead of 24.5 produces no row at all.
- **Fix:** either record whole-number lines and grade `actual == line` as a push (0 units, shown),
  or state on the page that such lines are excluded and log how many were skipped per day.

### 5. Scratches, postponements and "played 1 minute" are not distinguished — MEDIUM

- **Where:** `nba_paper.py:159-182` (`settle`), especially `:178-180`.
- **Issue:** a pending row is `void` if the player has no game-log row for that `game_date` and the
  date has passed. A scratch, a postponed or cancelled game, a game-log fetch that is incomplete,
  and a name or id mismatch are all the same thing: void with 0 units. Conversely a player who
  plays one minute is graded normally; there is no minutes rule (sportsbooks' own rules differ
  by book and market, and this ledger does not say which it follows). Voids are determined only by
  the data feed, after the fact, so a pick that would have lost can disappear if the feed omits the
  row.
- **Reproduction (reproduced):** a pending row for a player absent from the game log, on a past
  date, becomes `status == "void"`, `pnl_units == 0.0`.
- **Fix:** record why (`void_reason`: `dnp`, `postponed`, `no_data`); only void on `no_data` after
  a re-fetch; write down the minutes rule and apply it; show the void count on the Record page
  next to the record.

### 6. The settle job rewrites the whole file; the snapshot job appends to it — MEDIUM

- **Where:** `nba_paper.py:122-126`, `scripts/nba_props_settle.py:25-30`, `nba_paper.py:128-152`.
- **Issue:** settle is read-all, modify, write-all. If the snapshot job appends rows between the
  read and the write, those rows are lost. Rows that vanish this way are the "survivorship" failure
  mode, and it is silent. There is no lock and no row count check.
- **Fix:** take a file lock around both jobs, or keep the ledger append-only and write results as
  separate append-only "settlement" rows keyed by the pick id (also fixes finding 1).

### 7. Duplicate or competing picks on the same player and game are possible — MEDIUM

- **Where:** `nba_paper.py:154-156` (`_row_key` includes `line`).
- **Issue:** if the line moves between two snapshots, both lines become separate rows, and each can
  be a pick. The ledger records the first liquid price per key, so re-runs are safe, but a player
  can have two picks on one game. `append_rows` dedups only on the exact key.
- **Reproduction (reproduced):** line 24.5 then 25.5 for the same player, event and model: both
  rows are appended (second append returns 1). (In my run the second was not a pick; any line
  where the edge clears `MIN_EV_TO_RECORD` would be.)
- **Fix:** one pick per (event, player, model, stat, book): the first snapshot's pick stands, later
  lines are stored as non-picks.

### 8. Cherry-picking and survivorship: nothing prevents it, little shows it — MEDIUM

- **Where:** `ui/nba_record_tab.py:17-68`, `nba_paper.py:75` (integer lines), `nba_paper.py:252-255`
  (`load_fanduel_ledger`), `nba_alt.py` (X+ ledger), `nba_kalshi_ledger.py` (Kalshi rows).
- **Issue:** (a) the Record tab shows FanDuel points/model rows only; Kalshi rows are recorded
  but their results are never shown, and X+ picks appear as a one-line record with no units or
  accuracy, so a reader cannot tell if the unreported books or products do worse. (b) Model
  versions are added over time and each appears only from its own start date; a model that was
  tried and quietly removed leaves no row in the display unless its rows stay in the CSV (they
  would, but nothing says so). (c) Picks are only the rows whose edge clears
  `MIN_EV_TO_RECORD = 0.02`; the threshold is a code constant and could be changed after seeing
  results. (d) Early-only snapshots: if the PC is off during a game's window, that game is simply
  absent, and the page does not report games with no snapshot.
- **Fix:** show every ledger book, stat and model on the record page (even if empty), record the
  parameters (thresholds, model version, code commit) in the ledger row or in a signed manifest,
  and report "games on the slate that had no snapshot" per day.

### 9. What the Record tab shows versus the ledger — LOW (reconciles, with caveats)

- **Where:** `nba_record.py`, `ui/nba_record_tab.py`.
- **Checked:** record, units and return come from `nba_paper.summary` over settled FanDuel picks;
  the running-profit chart and day table come from `locked_picks` over rows with a `win` or `loss`;
  both sum the same `pnl_units`. Read from the code, not re-run: I did not find an arithmetic divergence, and the shaping
  functions have tests. Caveats: (i) all of finding 2;
  (ii) "Picks locked" counts every pick including pending and void, while "Record" counts settled
  only, so the headline tiles are not the same population; (iii) the accuracy verdict
  (`calibration_summary`) is over **all** settled lines, not just picks, and the page does not
  say so next to the record; (iv) `locked_picks` reads `STATS[s]` for each row's `stat` and will
  raise on an unknown stat string, which would blank the whole tab rather than one row.
- **Fix:** add a small reconciliation test or page footer: total rows = picks + non-picks;
  settled + void + pending = picks; units shown = sum of `pnl_units` in the file.

### 10. Display-only claims that are not enforced — LOW

- "Every pick was recorded before its game started" is shown in green whenever `after_tip == 0`.
  That is true of the file as it is *now*; see findings 1 and 3. The wording should be "in this
  file" until the log is tamper-evident.
- `MIN_LINES_FOR_VERDICT = 300` is a good guard, but it is applied to *lines*, which are heavily
  correlated within a game (several models price the same line), so 300 lines is far fewer
  independent trials than it sounds.

---

## What a public version needs

### A tamper-evident log

1. **Append-only rows with a hash chain.** Each pick row gets `prev_hash` and
   `row_hash = SHA-256(prev_hash || canonical_row_bytes)`; results are separate appended rows that
   reference the pick id. Rewriting any row breaks every later hash.
2. **A published daily digest.** After the last early snapshot each day, publish the chain head
   (and the day's snapshot files hash) to somewhere the operator cannot silently rewrite: a public
   git repo with signed commits, a social post, or an RFC 3161 timestamp authority. A stranger can
   then verify "this pick existed before tip-off" without trusting the operator.
3. **Enforce the pre-tip rule in code** (finding 2) and store the raw odds response with a hash.
4. **Freeze parameters** (model version, code commit, edge threshold) in each day's manifest.
5. **Publish the verification script** so anyone can recompute the record from the log.

### Data licensing (the feeds used today)

This is a factual list of what the code touches, not a licensing opinion; each source's current
terms must be read and, where needed, a licence obtained.

- **ESPN injury JSON** (`data/nba_injuries.py:18`): an undocumented endpoint. The module's own
  docstring says it is "fine for a personal tool but not a licensed source". Terms of use for
  ESPN's APIs generally restrict commercial use and redistribution.
- **NBA CDN headshots and logos** (`data/nba_live.py:87`, `tracking/nba_parlay.py:42`):
  hot-linked images of players and NBA/team marks. Player likenesses and league and team trademarks
  are protected, and the NBA's terms restrict commercial use. A product that sells projections
  next to them needs a licence or should drop them.
- **`nba_api` / stats.nba.com and the NBA live feed** (`data/nba_stats.py`, `data/nba_live.py`): `nba_api`
  is an open-source client for NBA's unofficial endpoints; the library's licence does not license the
  data. NBA data for commercial use is normally licensed, and the NBA's terms of use should be
  checked before any commercial or public redistribution.
- **The Odds API** (free tier): the README already notes the free tier is for personal use; a
  public product needs a paid plan and a check of whether displaying or archiving bookmaker prices
  is allowed.
- **Kalshi market data** (`data/kalshi.py`): check Kalshi's API and market-data terms for
  redistribution and display, and note the prices recorded are before trading fees.
- **Sportsbook names.** Using FanDuel's name and prices describes a third party's product and
  should be reviewed for trademark and "implied endorsement" issues.

### Responsible gambling and legal points (US)

**This is not legal advice. A lawyer licensed in the relevant states must review the product,
the marketing and the terms before anything is public.** Points to raise with them:

- **Regulation is state by state.** Sports wagering is legal in some states and not others, with
  different rules for advertising and for "information" products. Whether publishing betting
  projections or picks is regulated (and whether a licence or registration is needed) depends on
  the state and on whether the product is paid, free, or tied to a sportsbook through affiliate
  links.
- **Advertising and claims.** The FTC's rules on endorsements and on unsubstantiated earnings
  claims, state consumer-protection laws, and gambling-advertising codes can apply to statements
  such as "profit", "edge" or "beats the market". Past results do not guarantee future results; the
  record page should state that plainly and show losses as prominently as wins.
- **Affiliate and sponsorship disclosure** if any link to a book earns a commission.
- **Age and location.** Wagering products are 21+ in most states (18+ in a few); a public product
  should have age gating and not target minors.
- **Responsible-gambling messaging.** The footer already shows "1-800-GAMBLER". Regulators and
  sportsbooks commonly expect a visible helpline, and some states require specific wording; a
  lawyer should confirm which. Avoid language that urges larger or more frequent bets
  (the "Bigger payouts" style should be reviewed in that light).
- **Prediction-market products.** Whether sports event contracts such as Kalshi's are treated as
  federally regulated swaps or as gambling is actively contested between the CFTC and some states.
  Presenting Kalshi prices as a place to bet should be reviewed before launch.
- **Privacy, terms of service and data protection** if accounts are added (roadmap item 4).

---

## Appendix: reproduction script

Run from the repo root against `main` (it writes only to a temp directory):

```python
import sys, tempfile, datetime as dt, pathlib
sys.path.insert(0, "src")
import pandas as pd
from edgefinder.tracking import nba_paper, nba_record
d = pathlib.Path(tempfile.mkdtemp()); path = d / "log.csv"
ev = {"event_id": "e1", "commence_time": "2026-11-04T00:00:00+00:00",
      "home": "New York Knicks", "away": "Boston Celtics"}
lines = [{"player": "A", "line": 24.5, "over_odds": -110, "under_odds": -110}]
pred = {"A": {"mean": 30.0, "player_id": 1}}
# recorded one hour AFTER tip-off: accepted
rows = nba_paper.build_ledger_rows(ev, lines, pred, "2026-11-04T01:00:00+00:00", "2026-11-03")
print(nba_paper.append_rows(rows, path=path), rows[0]["pick_side"])        # 1 over
games = pd.DataFrame({"player_id": [1], "game_date": [pd.Timestamp("2026-11-03")], "pts": [20.0]})
snaps = pd.DataFrame(columns=["phase", "event_id", "player", "fetched_at", "line", "over_odds", "under_odds"])
nba_paper.save_ledger(nba_paper.settle(nba_paper.load_ledger(path), games, snaps, dt.date(2026, 11, 5)), path)
led = nba_paper.load_ledger(path)
print(nba_paper.summary(led)["record"], nba_record.integrity(led)["after_tip"])   # 0-1 1
raw = pd.read_csv(path); raw.loc[raw.result == "loss", ["result", "pnl_units"]] = ["win", 0.909091]
raw.to_csv(path, index=False)
led = nba_paper.load_ledger(path)
print(nba_paper.summary(led)["record"], nba_record.integrity(led)["after_tip"])   # 1-0 1: edit not detected
print(nba_record.cumulative_units(nba_record.locked_picks(led)))                  # after-tip pick counted
```
