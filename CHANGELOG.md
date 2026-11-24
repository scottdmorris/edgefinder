# Changelog

Newest first. Dates are when the work was committed.

## Unreleased

### Fixes to the Parlay game pages and the X+ recording

- An old `?game=` link for a game not on the board no longer empties the suggested slip; the
  page treats it as the games list throughout.
- A game's page whose chosen stat tab disappears after a switch of book or day now opens its
  first stat, on its Over / Under lines, instead of saying it has no props.
- The Parlay home shows "See … lines" for another price source when this one has no lines,
  without first typing a name.
- If the points models fail to build during a snapshot, PropLine's rebounds, assists and threes
  lines and their X+ rungs are still priced by the rolling average, which needs only history.
- Validation: `pytest` 1,515 passed; `ruff check` clean; `vitest` 92 passed; `npm run build`
  (tsc and vite) succeeded.

### Parlay works like a sportsbook: pick a game, then bet
- The Parlay screen opens on a list of the day's games. Tapping one opens that game's own
  page (`#/parlay?game=...`, so Back returns to the list): the matchup with tip time and
  moneylines, a tab per stat it has, then each team's players with Over/Under price buttons.
  The "All props" list is gone; a "Find a player" search finds anyone's props across games.
  The suggested slip and quick adds sit under the games (or under the game).
- Where a stat has both, a switch moves between its Over / Under lines and its X+ ladder
  ("Points X+"), shown as a row of rung buttons (20+ · 25+ · 30+ with prices).
- FanDuel's points X+ rungs are recorded again. They stopped on 2026-11-17 when The Odds
  API's extra request for them was dropped to save its quota; they now come free from
  PropLine's existing request, priced by every points model into the same X+ ledger as
  before, so they reappear on the board from the next early snapshot.
- Validation: 1,514 Python tests pass (1 new) and ruff is clean; 90 web tests pass (game
  page tests rewritten) and the TypeScript check is clean. Checked in the rebuilt app:
  games list, a game's page, and the browser Back button. The X+ switch is covered by
  tests only until the first FanDuel rungs are recorded.

### Moneylines and win chances on the game cards
- Each game card on the Parlay screen shows both teams' moneyline and the market's win
  chance with the book's margin removed ("MEM +150 39%"). When you open a game, each team's
  heading shows the same numbers, with a note that they come from the FanDuel (or DraftKings)
  moneyline and are the market's view, not a model's. A game with no archived moneyline
  shows no odds.
- Source: PropLine. The snapshot job's single bulk request now also asks for `h2h`, so
  FanDuel's and DraftKings' moneylines arrive with no extra request and no Odds API credits.
  They are archived for each due game before tip-off in `data/nba_moneylines.csv`, and a
  failure there is logged without affecting the props archive or the snapshot.
- Display only: moneylines never enter the published record, the X posts or the slip trials.
  No model win estimate was added.
- Validation: new pytest tests (parsing, no-vig math, archive, book choice, snapshot
  failure) and API tests pass with the full suite (1,513 passed), along with ruff, 3 new
  vitest tests plus the full web suite (89 passed), `npx tsc --noEmit` and `npm run build`.
  Parsing was checked against today's live PropLine payload. The cards and game view were
  checked in the rebuilt app using sample prices, because tonight's games had already tipped
  and none had been archived.

### Simpler, sportsbook-style prop rows
- Each prop row now reads like a sportsbook: the player, the game and their season and
  last-10 average, then two price buttons with the line on top and the price underneath
  ("O 24.5 / -110"). The implied chance, the model's view and projection, hit rates, the
  other book's price, quote warnings and the alternate lines moved behind an ⓘ button,
  and the help text above the list is one line.
- On a phone the buttons are narrower so names and averages fit instead of being cut off.
- Validation: the 9 prop-list tests were rewritten for the new layout and pass with the
  other web tests and the TypeScript check on these files; checked in the rebuilt app at
  desktop and phone width (375px, no sideways scroll).

### Paper trial: X+ lines for rebounds, assists and threes
- The early snapshot reads FanDuel's "X+" rungs for rebounds, assists and threes from
  PropLine's milestone markets (same request as before) and prices them with the Simple
  model into their own ledger, `data/nba_alt_stats_log.csv`. The settle job grades them
  from box scores and reports each stat's picks, record and units in its log.
- It is a trial only: the board, Record screen, X posts and slip trials never read it, and
  the points X+ ledger is untouched. Its pick rule is the points X+ rule without the ban
  on the Simple model, since that ban was measured on points only.
- Validation: 1,504 Python tests pass (7 new) and ruff is clean. A live dry run into a
  scratch file priced 159 rungs on the one game not yet started, 11 of them picks.

### Sportsbook-style games on the Parlay screen
- The game filter is now a row of game cards in tip-off order, each with both teams'
  logos, the tip time and how many players have props, with scroll arrows on desktop. It
  sits right above the props and stays pinned while scrolling them.
- Every prop row shows the player's season and last-10 average for that stat (it was only
  in a hover tooltip before).
- Choosing a game lists its props by team, away side first, each player once with every
  stat he has a line for. Players start folded to one line ("PTS 17.5 · REB 2.5 · ...")
  to keep the page short and open with a tap; a player already on the slip starts open.
  A stat filter and a player search narrow it.
- The board API now sends each game's tip time, team codes, logos and player count, and
  each leg's team.
- Validation: 1,497 Python tests pass (1 new), 85 web tests pass (5 new), ruff and the
  TypeScript check are clean, and the screen was checked in the rebuilt app on the
  2026-11-23 slate.

### What the misses say, in the nightly settle report
- The settle log gains a section per model for FanDuel points: picks split by over and
  under (win rate, units, and how far the actual score landed from the projection), split
  by price, and how much of the model's disagreement with the line came true across every
  settled line. It is read-only: a lesson from it becomes a new model version, never a
  change to the models being graded.
- Validation: 1,496 Python tests pass (7 new) and ruff is clean; the section was printed
  from the real ledger and matches a separate scratch analysis.

### Every prop on a player's page, with his averages
- A player's "On the slate" box now lists each FanDuel line he has (points, rebounds,
  assists, 3-pointers) in a table beside his season and last-10 averages for that stat
  and each model's projection, instead of the points line alone.
- Validation: 1,489 Python tests pass (1 new), 80 web tests pass (1 new), ruff and the
  TypeScript check are clean; checked on the rebuilt app with the live 2026-11-23 slate.

### FanDuel rebounds, assists and threes picks
- The early snapshot now prices FanDuel's rebounds, assists and threes main lines from
  PropLine into the ledger (book `fanduel`, their own stat). The rolling-average model
  (Simple) prices them, since it is the one model that projects every stat. Points still
  come only from The Odds API.
- They are graded from the box scores and closed from PropLine's last pregame line, with
  the fair close averaged across FanDuel and DraftKings, the same way points are.
- They show on the board and in the record's by-book table. The Picks screen, player and
  team pages, nightly review and per-model record stay FanDuel points (that screen's table
  has no stat column yet). The README record, fingerprint, X posts and slip trials are
  unchanged: they already read FanDuel points or context-v2 only.
- Validation: 1,488 tests pass (4 new), ruff clean. A live pricing run into a scratch
  ledger priced 161 lines across the next day's 5 listed games, 12 of them picks.

### PropLine archived as a second source for all four stats
- The Odds API's free quota only covers FanDuel points. Each snapshot run now also makes one
  PropLine request (free plan: 1,000 a day) and saves FanDuel and DraftKings main lines for
  points, rebounds, assists and threes, for the games due that run, to
  `data/nba_propline_lines.csv` with NBA player ids. Games past the Odds API budget are
  included. Picks, the ledger and the published record are unchanged.
- Skipped when no key is set (`data/propline_key.txt`, git-ignored, or `PROPLINE_API_KEY`);
  a PropLine failure is logged and never stops the snapshot. The key goes in a header and
  never appears in an error.
- Validation: 1,484 tests pass (8 new), ruff clean. A live side-by-side pull on Nov 22
  matched The Odds API's FanDuel points lines on all 14 players of one game (DraftKings: 9
  of 14 the same, pulled a second or two apart). A live archive into a scratch file
  matched 5 of the next day's 10 games (the rest had no lines posted yet).

### A cut-off record publish is finished automatically
- Each snapshot run now checks for a morning publish that never reached GitHub and finishes
  it: it commits the README table and fingerprint exactly as the 9:00 job staged them (the
  fingerprint is never recomputed, so it still matches the morning post) and pushes. A
  record commit whose push failed is pushed the same way.
- It acts only on the job's own work. A README edit outside the record table, a README edit
  with no new fingerprint, or any unpushed commit that is not a record commit is left alone.
- Validation: 1,477 tests pass (6 new, against a real temporary git repo and remote), ruff
  clean.

### Odds API reserve lowered to 50
- Snapshots now stop at 50 remaining requests instead of 100, so November's free quota
  should last to the Dec 1 reset rather than going dark a day or two early. Nothing in
  the web app spends Odds API requests, so the smaller cushion only affects manual runs.
- Validation: 1,471 tests pass, ruff clean.

### The morning post holds its fingerprint until the record is published
- On Nov 22 the 9:00 publish was cut off mid-commit, but the morning post still named that
  day's fingerprint, which nobody could find on GitHub yet. Now, when the record does not
  publish, the card leaves the fingerprint off and `<day>-reply.txt` is not written (an
  earlier one for that day is removed). The log line says the reply was held.
- That day's record was published by hand from exactly what the job had staged, so the
  fingerprint in its reply matches GitHub.
- Validation: 1,471 tests pass (27 for posts and settle), ruff clean.

### Faster Parlay quote enrichment
- Index ledger rows, price snapshots and player history once per request instead
  of scanning whole tables for each leg. Refresh prices and check eligibility
  against the current clock on every request.
- Verified exact output parity across 12,016 leg evaluations on FanDuel,
  DraftKings and Kalshi. On the larger measured FanDuel board, median warm
  response fell from 3.00 s to 2.22 s. Both timed boards returned identical JSON.
- Existing trial protocols accept this verified refactor's fingerprint while
  retaining their original protocol and continuing to reject other revisions.
- Validation: 66 focused Python tests and Ruff passed. The existing Long shot
  protocol was checked on a read-only copy of the local database.

### X card fixes from the first live days
- A card that Edge fails to draw now raises an error instead of passing as done. Before,
  the check only asked whether a PNG existed, so an earlier card at the same path counted
  as the new one. Edge now draws into a scratch folder and the file is moved into place only
  when it comes out; a failed draw leaves the earlier card untouched.
- Tonight's caption says "an 8-leg Long shot", not "a 8-leg".
- The Long shot panel's label no longer wraps: "Kalshi" moved to the line under the payout.
- Validation: 1,469 tests pass and ruff is clean; Nov 19's card redrawn from real data and checked by eye.

### Tonight's card, and a punchier morning post
- New afternoon post, `scripts/tonight_post.py`: the Sharpest model's FanDuel points picks
  for today, as already locked in the log (player, game and tip, pick, odds, chance and
  edge; up to 6 rows, then "+N more in the app"), plus the Long shot trial's Kalshi slip
  beside them when one is recorded. Saved as `data/posts/<day>-tonight.png` and `.txt`.
  Each snapshot run refreshes it, since later games lock later, and it redraws only when the
  picks or the slip change. The morning post grades the same picks.
- The morning caption now leads with the result ("5-3 last night, +1.45u 📈"), states the
  season with its losses, points to tonight's card, and asks "Tail or fade?". The GitHub
  link and the fingerprint moved to `<day>-reply.txt`, to post as the first reply.
- The record card reads on a phone: bigger table headers, labels and footer, no small
  column key, and no URL on the card.
- `--preview` on either script draws the post as it would read in an X feed, with the
  reply under the morning post.
- Validation: 1,466 Python tests passed with coverage (5 new for tonight's card, 3 new or
  updated for the morning post) and ruff is clean. Both cards and feed previews were
  rendered with Edge from real ledger data (Nov 16 results, Nov 17 picks) and checked by
  eye, plus a sample tonight's card with a Long shot panel.

### A daily record card for X
- `scripts/daily_post.py` makes the morning post for @BalllKnowledge from the last graded
  night: a 16:9 card (2400×1350 PNG) in the app's colours and logo, and a caption under
  280 characters, saved to `data/posts/<day>.png` and `.txt` (git-ignored). Nothing is
  posted automatically.
- The card leads with one fixed model, Sharpest (the app's default), so the headline is
  never the night's luckiest model. All four models follow with last night's and the
  season's record, units and how often they beat the closing price. Losses show in red.
  Graded Long shot and higher-hit trial slips appear as result lines. The footer carries
  the published fingerprint, where to verify it, and "paper bets, not betting advice, 21+,
  1-800-GAMBLER".
- `--preview` also draws `<day>-preview.png`: the post as it would read in an X feed,
  with the caption and the card together.
- The card is HTML (`scripts/daily_post_card.html`) saved as a picture by Microsoft Edge
  running headless, so it uses real fonts and the SVG logo without new dependencies.
- The 9:00 settle job makes the post after it publishes the record, so the card carries
  the new fingerprint. A failure is logged and never fails the settle, and a failed
  settle makes no post.
- Validation: 1,458 Python tests passed with coverage (11 new: 8 for the post, 3 for the
  settle hook) and ruff is clean. The Nov 16 card was rendered with Edge and checked by
  eye, along with a sample that shows trial results.

### Long shot: a many-leg slip, tracked on paper
- New **Long shot** betting style on the Parlay screen: one slip of 8 to 10 of the
  likeliest legs that are each worth betting on their own and pass the quote checks, one
  bet a player and at most two a game (the snapshot covers at most 8 games), priced with
  the measured same-game correlations. It is not built for a single game. Kalshi usually
  has enough legs; FanDuel and DraftKings rarely do, and then it says so.
- Tested first on last season's markets (`scripts/nba_many_leg_backtest.py`,
  docs/MANY_LEG_BACKTEST.md). Every extra leg made the return worse. The 10-leg,
  two-a-game rule won 18% of nights at a typical +352 and returned -32% at Kalshi prices
  (95% interval -64% to +3%). The card says this under the style switch.
- A second frozen paper trial, `long-shot-v1`, records the first qualifying Kalshi slip
  each day from Context v2 alongside the higher-hit trial. Either trial failing never
  stops the other, and the nightly capture now also runs on Kalshi-only snapshots. The
  Record tab shows it as its own card.
- Chances under 10% now show one decimal on the suggested slip.
- Note: both trials freeze a hash of the slip code (nba_parlay.py, service.py,
  suggestion_service.py and others) when they record their first slip. After that, a code
  change to those files stops new entries until a new trial ID is used. Neither trial had
  recorded a slip yet, so this change breaks nothing.
- Validation: 1,447 Python tests passed with coverage (13 new) and ruff is clean; all 79
  web tests (2 new), type-check and lint passed. The backtest script was run on both
  market sets above.

### Desktop and mobile audit fixes
- Slip estimates immediately reprice after refreshed odds, probabilities or board
  revisions; superseded estimates stay hidden while the new request runs.
- Mobile slips use a named native modal with contained keyboard focus, Escape dismissal,
  restored opener focus, scroll locking, safe-area padding and unique Stake labels.
- Player/team profiles follow query-only URL navigation. Search catalogs and Last night
  distinguish failures from valid empty data, offer retry and retain available content.
- Added keyboard radio navigation, active search-option announcements, readable player
  headers, and narrow-screen wrapping for Review, Picks, slip and audit details.
- Chart values are available by touch/keyboard and through equivalent data tables;
  improved axis readability, table headers, scroll-region focus and graphic semantics.
  Saved slips remain visible when the live scoreboard is empty or unavailable.
- Browser verification also exposed a fresh comparison returning a NumPy boolean;
  convert it to a JSON boolean so the Parlay board cannot fail serialization.
- Validation: all 77 web tests, lint and production build passed; 49 focused Python
  tests and Python lint passed. All 32 desktop/mobile viewport checks have no document
  overflow or automated axe findings after rechecking Picks. Browser checks verified
  modal focus/Escape/labels, repricing, profile navigation, search and review recovery.
  Physical-device and Safari testing remain unverified.

### DraftKings as a price source on the Parlay screen; a tidier line under each prop
- DraftKings lines were archived but never priced by the models, so the Parlay screen
  could not offer them. From the next early snapshot, every model prices DraftKings' lines
  too (they come back on the same request, so this costs nothing) and they are recorded
  with `book="draftkings"`. DraftKings then appears next to FanDuel and Kalshi under the
  price source. DraftKings picks are graded against the sportsbooks' fair close and get
  their own rows in the Record screen's by-book and fair-close sections; the headline
  record and the published README table stay FanDuel's. (The first snapshots after the
  change, on Nov 17, already priced DraftKings.)
- With DraftKings chosen, each quote is compared with FanDuel's price, the mirror of the
  FanDuel view. Comparisons apply to sportsbook over/under lines when both books
  have a quote. Quick Adds show the selected source's odds for matching bets and
  label the FanDuel estimate. The missing-stat shortcut prefers Kalshi.
- The five lines of quote detail under each player are now one: the hit rate over his last
  games, his usual range, and the other sportsbook's price with a one- or two-word reading
  ("other number", "pays more there", "old price"). Quotes left out of suggestions get a
  "Not suggested · why" toggle with the reasons and timestamps; the general caveats about
  hit rates and injuries are stated once above the list.
- The README now lists three price sources, drops the X+ ladders from the Picks
  description, and gives the current test count.
- Changing the suggestion code also changes its frozen trial fingerprint. The local
  archive had no frozen trial. Installations with an existing fingerprint retain
  their recorded results and reject new entries under the old fingerprint.
- Validation: 1,434 Python tests passed with 97% coverage. Ruff, 77 web tests,
  web lint and production build passed.
  `verify_record.py` reported an intact chain with all 17,391 ledger rows matching.

### Shared live updates, on-demand screens and API profiling
- The header and Live page now share one scoreboard request loop, using the fastest
  requested interval without duplicate requests. Hidden tabs pause; failed refreshes
  retain the last successful board and its receipt time.
- Screens load on demand with an accessible loading state. A failed screen offers
  manual reload while navigation stays available. The default Parlay opening uses
  about 21% less raw JavaScript than the previous all-screen bundle.
- Added an offline API benchmark with cold/warm measurements and optional profiling;
  it blocks outbound connections and reads suggested offers without writing them.
  Measurements and limits are recorded in docs/PERFORMANCE.md. Quote enrichment is
  the measured backend hotspot; the frozen trial recipe and cache TTLs are unchanged.
- Validation: all 53 web tests, web lint and production build passed. The local API
  benchmark ran across eight routes; Python lint passed for the benchmark script.

### Eight games a night on FanDuel instead of six; FanDuel's X+ lines are no longer fetched
- The snapshot job bought FanDuel prices for only the first 6 games a night (by tip
  time), so on busy nights the late West Coast games got Kalshi prices only. On
  2026-11-15 that left out Thunder at Kings and Hawks at Bucks.
- The extra request each FanDuel "X+ points" game cost (up to 4 a night) now pays for 2
  more games instead: 8 games x 2 snapshots is 16 requests a night, the same as before.
  X+ points picks had the worst record of anything tracked. Kalshi still records its X+
  rungs for free, and the existing FanDuel X+ ledger is still settled.
- Validation: 1,423 Python tests passed; ruff clean; a snapshot dry run was clean.

### Court Vision identity, darker theme and clearer team pages
- Added the selected Court Vision basketball-eye logo as scalable SVG for the app,
  favicon and wordmark. Preserved the concept sheet and Courtside IQ alternative.
- Applied a near-black theme with charcoal-blue cards, a restrained header glow and
  brighter muted text. Team headers retain their team colour.
- Added local FanDuel, DraftKings and Kalshi brand assets to price-source selectors and
  comparison rows. Badges preserve accessible names and fall back to text if an image
  fails. Asset sources are documented in web/public/books/SOURCES.md.
- Team pages lead with matchup and prop context; full rankings sit in an expandable
  section. Opponent totals use descriptive labels rather than implying betting-line
  success. Winning-margin charts have clearer scaling and focus/hover score details.
- Validation: all 43 web tests passed, including badge fallback/accessibility tests;
  lint and production build passed. The earlier Teams layout was inspected in-browser;
  the final darker palette/logo preview could not be verified because the browser timed out.

### Combined-work review hardening
- Changing the trial recipe now blocks only new trial entries: old suggested slips and
  their frozen protocol remain readable and gradable after ordinary code updates.
- Suggested-slip search caches now include the current blended probability as well as
  quote identity and odds. A change to the other side of a two-way price cannot silently
  reuse a suggestion scored with the previous market probability.
- A one-sided price refresh is excluded from higher-hit suggestions rather than being
  treated as fresh two-sided evidence with the old market estimate.
- Preserved and reviewed the concurrent Teams additions: matchup comparisons, opponent
  stat ranks, recent minutes and injury badges, line hit rates, exclusion of unfinished
  games and already-completed slate games, and three-game minimum with/without splits.
- Validation in an isolated checkout of the staged snapshot: 1,420 Python tests passed
  at 96.84% coverage, 41 web tests passed, web lint and production build passed, and ruff
  and Bandit were clean. The final Teams adjustment also passed a targeted 76-test rerun.

### Offered-slip record, price comparison, and a prospective higher-hit trial
- Added a Higher hit rate style, selected by default in the app: at most two legs,
  at least 60% estimated joint chance and 1.30 simulated decimal return. It can return
  no suggestion. A model target is not an observed win rate or a profitability claim.
- Each unique pregame suggestion returned by the API is frozen with its exact legs,
  prices, probability and simulated payout in a separate SQLite paper archive. Repeat
  requests deduplicate; the morning job grades hits, misses and voided legs. The Record
  screen separates all offered suggestions from the frozen trial. This does not measure
  actual visitor impressions, clicks or placed bets, and payouts are products of leg
  prices rather than executable sportsbook parlay quotes.
- Props show FanDuel and DraftKings numbers, odds, return multiples and timestamps.
  Different numbers are explicitly not comparable; stale comparisons are labelled.
  Same-number FanDuel prices can refresh from newer recorded snapshots without changing
  the quote identity; a moved number is excluded from higher-hit suggestions.
- Props also show prior-game hit rates and historical result ranges, with pass reasons
  for insufficient history, stale prices, unstable minutes, role changes and layoffs.
  These are history checks, not confirmation of tonight's injury status.
- Frozen trial higher-hit-v1: first qualifying Context v2/FanDuel two-leg slip per day,
  different games; review after 200 graded slips across at least 30 graded game days.
  Protocol and selection-code hashes are stored before results; changed rules require a
  new trial ID. See docs/HIGHER_HIT_TRIAL.md for scoring and limitations. No backfilling.
- Validation: the full Python suite passed (1,411 tests, 96.99% coverage), with focused
  archive/evidence/API regression tests rerun after final refinements. All 37 web tests,
  lint and production build passed; ruff and Bandit were clean. A live-board smoke check
  returned 418 legs with history checks and recorded DraftKings comparisons. The original
  pick log remained intact with all 13,509 ledger rows matching. No historical suggestions
  were retrospectively added to the new record.

### Team pages rebuilt for props
- Fixed: a game still in progress counted as a loss on the team page (Atlanta showed 7-7
  and a "nan0" streak during its game). Only finished games are counted now, everywhere on
  the page. A slate game the team has already finished is no longer shown as "next".
- New: the next game side by side with the opponent (record, points for and against,
  offense, defense and pace ranks) and what the opponent gives up per stat.
- New: "What opponents put up against them": points, rebounds, assists and 3-pointers
  allowed per game, ranked, and labelled soft, average or tough.
- New: each points line on the slate shows the projection minus the line and how many of
  the player's last 10 games went over it.
- New: a form chart of the last 10 margins; injury badges and last-5-games minutes (with
  a marked rise or fall of 2+ minutes) on the roster.
- The with/without split now needs 3 games on each side, not 2.
- Validation: 17 team tests in Python and 8 on the web pass; web type-check, lint and
  build pass; checked in a browser on live data.

### Teams on the Players screen
- The search box now finds teams as well as players (by name or code, e.g. "celtics" or
  "BOS"), and a player's team name links to the team. A team page shows the record (home,
  away, last 10, streak), points scored and allowed with league ranks, offense, defense and
  pace ranks from estimated possessions, the team's players on the latest FanDuel slate
  with their lines and the `context-v2` projection, who is out on the ESPN injury report,
  the roster with per-game averages, and recent results.
- For each regular ruled out, the page shows how his teammates scored and how many
  minutes they played in this season's games with him and without him. Stats sites such
  as StatMuse show team stats and against-the-spread records but not this next to
  tonight's lines.
- New routes `/api/teams` and `/api/teams/{code}` (`src/edgefinder/api/teams.py`).
- Validation: 10 new Python tests and 4 new web tests pass; web type-check, lint and build
  pass; the team page and search were checked in a browser against live data.

### Settlement and closing-price review fixes
- Missing players are voided only after the specific matchup has full, matching team
  minutes in both sides of the game logs. Other games on the same date, partial downloads,
  and unknown matchups leave the row pending. Applies to main picks, X+ picks and gap bets.
- Closing prices must have a valid fetch time strictly before tip-off. Historical Kalshi
  snapshots use the ledger's event time. Fair-close values are recalculated so a rejected
  price cannot leave a previously saved value behind.
- The public-record publisher retries pushing an existing commit even when its files have
  no new changes, allowing recovery from a failed push without creating another commit.
- The Record screen now shows value against the fair closing chance after removing the
  book's margin, with its sample size and how often it was beaten. Older price-movement
  measurements are preserved in the ledger.
- Validation: the full Python suite passed (1,392 tests, 96.29% coverage); after the
  final rounding-tolerance adjustment, all 40 settlement/closing/publishing regression
  tests passed again. All 31 web tests passed, lint and production build passed,
  ruff and Bandit were clean, and the pick log remained intact (13,509 rows match).

### Picks and gap bets are graded against the fair closing price
- Every settled pick now gets `clv_novig_pct`: its payout times the market's fair closing
  chance of that side, minus 1. The fair close removes the book's cut from each book's last
  price before tip-off and averages the books that closed on the same number (FanDuel and
  DraftKings for FanDuel picks; Kalshi's own close for Kalshi picks). Positive means the
  price taken beat where the market finished after the margin, which predicts profit far
  sooner than wins and losses. The older `clv_pct`, against FanDuel's own price with the
  margin left in, is kept.
- Both gap logs get the same figure for over and under bets (X+ bets have no two-sided
  close). Older gap log files are upgraded to the new column before rows are added.
- The settle report shows the average, how many bets it covers, and how often the fair
  close was beaten, for each model and each gap log.
- First reading, computed on everything graded to 2026-11-14 (it is saved to the ledger by
  the next settle): FanDuel picks average -4.9% to -5.6% against the fair close for every
  model, and beat it 3-6% of the time, which is about the size of FanDuel's own margin.
  Kalshi picks average -0.7% to -1.0% and beat it about 30% of the time. The FanDuel-vs-
  Kalshi gaps average -1.2% (24 measured) and the DraftKings gaps -6.8% (17 measured).
  So far no model's picks or gap bets beat the fair close.
- Also: the X+ ledger's text columns are now read as text, which silences a pandas
  mixed-type warning.
- Validation: 1,376 Python tests passed, 13 of them new; ruff clean.

### FanDuel-vs-DraftKings gaps are graded like the Kalshi ones
- At each early snapshot, every FanDuel-vs-DraftKings disagreement "worth a look" is now
  logged as a FanDuel bet in `data/book_gap_log.csv`: on the same number, the side FanDuel
  pays 3%+ more for than DraftKings' fair chance; on numbers a point or more apart, the side
  FanDuel's number makes easier (its over when its number is lower, its under when higher).
  The first call on a bet stands, and nothing is logged once a game has started.
- The 9:00 settle grades them at a flat 1 unit and reports the record, split into "better
  price" and "other number". Nothing about picks or the record changes.
- Backfilled from the early snapshots already archived: 29 bets, 18 graded so far (9-9,
  -1.21 units). 28 of the 29 are "other number" bets. Far too few to mean anything yet.
- Validation: 1,363 Python tests passed with 97% coverage, 9 of them new; ruff clean.

### The public record updates itself every morning
- The README's record table and the published fingerprint in `record/DIGESTS.md` were only
  refreshed by hand, so they were always a few days behind. The 9:00 settle job now
  refreshes both and commits and pushes those two files, and nothing else
  (`scripts/publish_record.py`, run by `nba_props_settle.py --publish`). Anything else
  changed or staged in the folder is left alone.
- Nothing is published when the ledger no longer matches its log. A failed push is written
  to the settle report but never fails the settle. Git is told never to wait for a password
  prompt, so an unattended run cannot hang.
- The README table now sits between `<!-- record:start -->` and `<!-- record:end -->`
  markers; only that part is rewritten.
- The scheduled tasks were re-registered (`scripts/install_nba_tasks.ps1`) so the settle
  task passes `--publish`.
- Validation: 1,354 Python tests passed with 97% coverage, 10 of them new; ruff clean. The
  publishing step has not yet run for real.

### The two oldest models no longer make X+ points picks
- `ewma-v1` and `minutes-v1` still price every X+ points line, so the record keeps judging
  them, but none of their prices counts as a pick any more. Over their first 1,253 graded
  X+ picks (to 2026-11-13) they returned -23.7% and -26.0%, against -6.7% and -5.4% for the
  two context models. Their single fixed spread overrates long shots, which is most of
  what an X+ ladder holds. Picks already recorded are unchanged.
- Validation: 1,344 Python tests passed, 5 of them new.

### Audit clean-up: Streamlit removed, safer saves, security and coverage checks
- **The Streamlit app is gone.** The React app is the product; `app.py`, the Streamlit
  screens and their tests are removed, along with the player-questions code only they
  used. The About screen went with it; its content is in `docs/METHODOLOGY.md`. Team
  colours moved to `data/team_colors.py` because the web API uses them.
- **The old odds client is gone.** Its MLB, soccer, UFC and Pinnacle functions were no
  longer called, and their error messages could include the request URL, which carries
  the API key. Only the key lookup and the quota reading remain.
- **Ledger saves are crash-safe.** The ledgers, the price-gap log, the job heartbeat, the
  caches and the saved box scores are now written to a temporary file and swapped in, so
  a crash or a sync client grabbing the file mid-write cannot leave half a file. A briefly
  locked file is retried.
- **Three small bugs fixed** (previously parked as expected failures): a negative Kelly
  multiplier can no longer produce a negative stake; removing the margin from a two-way
  price refuses a negative input; and a game whose id is all digits is no longer recorded
  again on every run.
- **Pillow upgraded from 12.3.0 to 13.0.0.** The dependency scan found two known
  vulnerabilities in the version that reads uploaded slip photos.
- **Checks added.** Python dependencies are pinned to exact versions, with
  `requirements-dev.txt` for the test and checking tools. CI now also runs the linter
  (ruff), a security scan (bandit) and fails if test coverage drops below 90%.
- Validation: 1,339 Python tests passed with 97% coverage (the count fell because the
  Streamlit tests were removed; 13 are new). ruff and bandit report nothing, and
  `pip-audit` reports no known vulnerabilities. A real photo read, a snapshot dry run and
  `scripts/verify_record.py` (log intact, all 9,440 rows match) were run afterwards.

### Tested and not adopted: matching training to the injury report, and more history
- The audit found that `context-v1` and `context-v2` are trained with every recent-roster
  player missing from a box score counted as out (about 52 lost minutes per player-game),
  while live they are fed the injury report (about 23). A new definition that matches the
  report was built (`known_only` in `models/nba_context.py`: already missed the previous
  game, still with the team, has played for it this season) and scored by
  `scripts/nba_context_v3_eval.py`, chosen on 2024-25 and scored once on 2025-26.
- **The mismatch costs nothing measurable, and the fix made things worse.** `context-v2`
  fed the report-like numbers scored 5.0887 against 5.0898 with its training numbers. A
  model trained on the matching definition scored 5.1138, worse by 0.025 (interval 0.017
  to 0.034). No `context-v3` was added and no live model changed.
- **More seasons of training data barely help.** Training on five seasons instead of two
  improved the error by about 0.006 points (interval 0.000 to 0.012 on 2025-26). The live
  models train on three; not changed.
- Caveat: there is no archive of past injury reports, so "what live looks like" is stood in
  for by numbers worked out from box scores.
- Validation: the two scripts above were run; 8 new tests cover the new definition; 1,513 Python tests passed (3 expected failures).

### A failed stats download can no longer void picks
- Settling used to void every pending line whose player had no box score once the day had
  passed. When the morning NBA download fails, an older saved file is used instead, so
  players who DID play would have been voided for good. Now a line is only voided when the
  game logs reach that day; otherwise it stays pending and the settle report says how many
  lines are waiting and where the logs end. Applies to the main ledger, the X+ ledger and
  the price-gap log.
- This had not happened: all 286 existing voids were checked against the box scores and
  none belongs to a player who played.
- The published fingerprint in `record/DIGESTS.md` is brought up to date (17,836 entries;
  the last one published was 813 on 2026-11-05), and the README record table now shows
  all four models over eight graded days.
- Validation: 1,505 Python tests passed (3 expected failures), 6 of them new.
  `scripts/verify_record.py` reported the log intact and all 9,440 ledger rows matching.

### DraftKings prices recorded next to FanDuel's
- The snapshot job now asks for DraftKings' player-points lines in the same request as
  FanDuel's. The Odds API charges per market and region, not per book, so this spends no
  extra requests. DraftKings' lines go to their own file (`data/nba_book_lines.csv`), for
  both the early and the closing snapshot.
- Each snapshot logs how the two books compare: how many players both list, and how many
  are "worth a look" (FanDuel pays 3%+ more than DraftKings' fair chance on the same
  number, or the two numbers are a point or more apart).
- Unchanged: picks, the paper ledger, the record and every screen are still FanDuel's.
  Nothing in the app shows DraftKings yet. A failure saving DraftKings' lines never stops
  the FanDuel snapshot.
- Validation: 1,499 Python tests passed (3 expected failures), 17 of them new. One real
  request for tomorrow's Knicks at Pacers game confirmed the cost is still 1 request with
  both books asked for, and returned 8 FanDuel lines but **no DraftKings lines**. Whether
  DraftKings had simply not posted that game yet, or does not supply player points on
  this plan, is not known; the next scheduled snapshot's log line will show it.

### Tested and not adopted: telling the models about the game
- Other modelers project the game first (who wins, by how much, how many points) and the
  players second. `scripts/nba_game_context_eval.py` tests that here: each team's expected
  points, the expected margin and the expected total, worked out from earlier box scores
  (there is no archive of sportsbook spreads and totals for past seasons), added to
  context-v2's inputs. Chosen on 2024-25, scored once on 2025-26.
- **It did not help.** Points error moved from 5.0898 to 5.0891 for the variant chosen on
  2024-25 (a gain of 0.0007, interval -0.0010 to +0.0026) and no variant's gain was
  distinguishable from zero; the log score was unchanged or slightly worse. No live model
  changed and nothing in the app is different.
- Why, as far as measured: the models already see the opponent's defense and the pace, and
  the expected margin built from box scores is a weak forecast (correlation 0.45 with the
  real margin). As a ceiling, a model handed the game's actual final score in advance
  improves by only 0.135 points of error, so a sportsbook's spread and total could deliver
  a fraction of that at most.
- Validation: 8 new tests for the game numbers (including that a game never sees its own
  score); 1,482 Python tests passed (3 expected failures). The ceiling figure came from a one-off check that
  is not in the repository.

### A Parlay screen that leads with one suggested slip
- **Suggested slip** is now the first thing on the page: one slip with its legs, the chance
  they all hit, and what $10 returns before fees. Safer / Balanced / Bigger payouts changes
  the style, "Another" steps through the other suggestions, and "Use this slip" puts it on
  your slip. It replaces the grid of idea cards.
- The day, price source and model collapse into one row of small pills; "Change" opens the
  full choices. The **game filter stays visible** as its own row of pills and narrows the
  suggestion, the quick adds and the props.
- **Quick adds** merges Model picks, Price gaps and Steady into one sideways row. Each card
  says which kind it is and why it is there, and a filter narrows to one kind.
- FanDuel and Kalshi offer different numbers. A model pick (made on FanDuel's line) can be
  added on Kalshi only when Kalshi lists the same bet; otherwise the card says "FanDuel
  line. Kalshi doesn't offer this number." instead of showing no button.
- Props are one line per player: the player and line, the other numbers to step through,
  the price's chance with the model's beside it (green when the model rates the bet higher,
  red when lower, by 2 points or more), then the Over/Under prices.
- Fixed: after the server had been running for a while, NBA's live scores could fail on
  every request until a restart. A failed request is now retried on a fresh connection. The
  cause is inferred (a new process always worked while the long-running one failed); the
  fix has not yet been seen to recover a failing server.
- Validation: 1,474 Python tests passed (3 expected failures); 30 front-end tests, lint and
  the production build passed. Checked in the browser on tonight's board at desktop and
  phone width, including filtering to one game. The Kalshi "doesn't offer this number"
  message is covered by a test only.

### A Live screen that keeps the score and your slip in view
- The chosen game's scoreboard now stays pinned at the top while the rest of the game
  scrolls under it. When one team is heavily outscoring the other it says so under the clock
  ("ORL on a 9-2 run": at least 8 points while giving up a third of that or less).
- **Your players in this game** sits directly under the score: each bet on your slip that
  belongs to the game, with its count against the target, a progress bar, its status, and
  the fouled-out / ejected / off-the-floor warning on the card. The count pops and the card
  flashes when a player adds to it. The whole slip, across every game, moved below the game.
- **Latest plays** on a live game's Stats tab, the newest four, with a link to all of them.
  Plays by players on your slip are highlighted there and on the Plays tab.
- In the score strip the team in front is bold and the team behind is dimmed.
- Validation: 1,476 Python tests passed (3 expected failures); 26 front-end tests, lint and
  the production build passed. Checked in the browser on a live game (Raptors at 76ers,
  first quarter) with a three-leg test slip: the pinned score, slip players and highlighted
  plays all showed. No scoring run or mid-game warning occurred while I watched;
  those are covered by tests only.

### A recommended model and a Last night review
- The Parlay screen now opens on the model that has been most accurate so far, instead of
  whichever sorts first. Accuracy is measured on the graded points lines every model priced
  for that price source, and a model is only recommended once 100 such lines are graded.
  The chosen model shows its graded record and a "Recommended" tag; "Compare models" lists
  the others with their records. Today that is Shot profile on both FanDuel and Kalshi.
- New **Last night** screen: for any graded game day, how many model picks hit, each
  model's record and units that night, the misses furthest from the projection, and every
  pick. A miss on a short night says so ("Played 8 minutes, usually 30").
- Last night also grades the slip you built in this browser for that day against the box
  scores, leg by leg, and marks the leg that sank it with the chance it showed when added.
  Slips placed outside the app are not included, and mid-game alerts are not kept.
- Validation: 1,470 Python tests passed (3 expected failures); 20 front-end tests, lint and
  the production build passed. Checked in the browser on real data: Parlay opened on Shot
  profile 36-30, and Last night showed Nov 10 (24 of 38 picks hit) and graded a two-leg
  test slip correctly.

### Kalshi prices for every game, not just the first six
- The snapshot job records FanDuel lines for the first six games of a night to protect the
  Odds API budget, and Kalshi's free prices used to be recorded only for those same six.
  Games past the budget now get Kalshi's prices too: once in the early window (2.5 to 4
  hours before tip) and once as a closing price in the last 90 minutes. This spends no Odds
  API requests. Those games appear on the Kalshi board and count in the Kalshi paper record;
  they have no FanDuel lines, model picks or price-gap entries.
- Unchanged: Kalshi markets with a wide spread or little trading are still skipped, which is
  why low numbers (a star at 10+ points) are often not on the board.
- Validation: 1,461 Python tests passed (3 expected failures). The job's dry run was clean.
  A rehearsal priced two real games that had no FanDuel snapshot into a temporary file (366
  rows, all with a projection) and left the real ledger untouched. The new path has not yet
  run on a real night; the first chance is the next slate with more than six games.

### Photo slip matching reads one-line bets correctly
- A bet printed on the player's own line (Kalshi's "Name: 8+ rebounds") is now matched from
  that line alone. Before, text from the following lines (players not on the board, other
  stats) could make a recorded bet come back unmatched.
- Validation: tested on a real 20-leg Kalshi screenshot. All 20 legs were read correctly;
  4 matched a recorded line (3 before this fix). The other 16 are not on the recorded board:
  9 player bets in three games the board does not have, 2 team-to-win bets, and 5 player
  bets at numbers the board does not record (4 below its lowest, 1 between two it has).
  1,455 Python tests passed (3 expected failures).

### Mid-game alerts, model picks on Parlay, and a shorter props list
- Live now warns when a player on your slip looks done for the night while the bet is still
  in play: **Fouled out** (6 fouls), **Ejected** (an ejection or 2 technicals), listed out by
  NBA's feed, or off the floor for a long unbroken stretch of game time (10 minutes for a
  starter, 16 off the bench). NBA's feed does not announce mid-game injuries, so a long
  absence is a warning ("may be hurt or benched"), not a diagnosis. The warning shows above
  the slip and outlines the bet.
- A live game's period now comes from its latest play, like its score and clock, so the
  scoreboard lagging at a quarter break cannot skew the alert's timing.
- Parlay shows **Model picks** for the day (FanDuel points lines where a model sees value)
  with an Add button, and they follow the Game filter. The Picks screen keeps the full table.
- Points, Rebounds, Assists and 3PM pills are always shown. When the chosen price source has
  no lines for a stat (FanDuel records points only), the screen says so and offers the other
  source in one tap.
- The props list shows the six biggest names until "Show all", and everyone once a game is
  chosen or a search is typed. Each card names its stat, and a line explains the two
  percentages.
- A sentence under the Model pills says what the chosen model does.
- Validation: 1,454 Python tests passed (3 expected failures); 17 front-end tests, lint and
  the production build passed. The alert rule was run against tonight's three live games and
  raised three warnings, including a starter with 5.6 minutes who had been off the floor for
  30 game minutes. No ejection or foul-out occurred to observe; those rules are unit-tested.

### Slips that survive price moves, and the pill layout restored
- A saved selection is now identified by the bet itself (game, player, stat, side, line), not
  its price. A later snapshot moving the odds no longer drops the leg or breaks Live tracking;
  the Parlay screen notes the old and new price and the slip uses the new one. Slips saved
  under the previous price-bound IDs appear once under "Review saved selections".
- Looking at another day, price source or model on the Parlay screen no longer replaces the
  slip Live is tracking. Live follows the slip you last changed.
- Parlay is back to pills: game day, prices, model and game filters; a pill strip for each
  player's alternate lines; Over/Under (or Yes/No) pill buttons. Price gaps, Steady and Ideas
  sit above the props again instead of inside a collapsed section. Player search and the
  "On my slip" filter stay. Stat pills list only stats the price source has lines for.
- Live is back to the horizontal score strip with the first game open under its team-colour
  header. Strip cards mark games that have bets on your slip. The freshness label no longer
  warns "Stale data" on finished games.
- The pill navigation returns in place of full-width underline tabs.
- Correction to the entry below: the optional AI parlay analyst it describes was removed
  before release and is not in the code. The app makes no language-model calls. The photo
  slip review (local OCR via `rapidocr`, `onnxruntime`, `Pillow`) was added and is not
  described below.
- Validation: 1,446 Python tests passed (3 expected failures); 17 front-end tests, lint and
  the production build passed. Checked in a browser against a fresh server on port 8001:
  Parlay at desktop and phone width, selecting a leg, and Live tracking that slip.

### Optional AI parlay analyst and live-feed recovery
- Added an on-demand AI analyst to the React Parlay screen, defaulting to three
  legs, +350 to +550 illustrative odds and Moderate risk. Results include short
  rationales and a risk flag; applying a recommendation is a separate action.
- Python filters existing estimated-positive-EV candidates, computes eligible
  combinations and enforces exact leg count, odds range and risk thresholds.
  This first version uses distinct players and games and a bounded shortlist.
- The OpenAI request uses a stable system prompt, pipe-delimited data, low reasoning
  effort, JSON mode, a 1,800-token completion budget, concurrency protection and a
  15-second interval between calls. Credentials and model selection stay server-side.
- Validate returned selections, odds, schema and word limits. Invented selections,
  changed quotes, stale UI requests, malformed responses and unavailable configuration
  cannot silently become slips. No automatic paid retries or simulated AI fallback.
- Include historical hit counts and today's available injury report; exclude players
  listed Out/Doubtful. Missing spread, pace, rest and matchup ranks remain explicit.
- Correct NBA live-feed compression headers to match installed decoder support and
  retry unreadable responses once across scoreboard, box score and play-by-play.
  Restarted the previously stale running server and confirmed real API responses.
- Added `AGENTS.md` requiring changelog updates for future user-facing changes.
- Setup and limitations are documented in README. Live model execution still requires
  `OPENAI_API_KEY` and `EDGEFINDER_AI_MODEL`; neither is configured in this environment.
- Validation: 1,450 Python tests passed (3 expected failures); all 15 front-end tests,
  front-end lint and the production build passed. Provider calls are mocked in tests;
  no paid model request was made without credentials.

### A clearer main app and a Live overview
- React/FastAPI is the documented main interface at port 8000, with a build-and-run
  launcher (`scripts/start_app.ps1`). Streamlit remains available for internal analysis.
- Live shows all games in a responsive grid with scores, clocks and tracked selections.
  Selecting a card opens its detailed game center. Final, pending and void states are labeled.
- NBA response receipt times survive API cache hits; the browser shows their age separately
  from its board refresh time. Missing game details, stale data and connection failures are
  visible even when a previous successful response remains on screen. Receipt times do not
  claim that the NBA source itself is current. Visibility refreshes cannot overlap a pending poll.
- Props come first, with player search that ignores accents, stat filters and a selected-only
  view. Price gaps, Steady and Ideas remain available under a collapsible suggestions section.
- Prop rows emphasize target, price and the chosen side's slip estimate; the market/model
  comparison expands on demand. Selecting No shows No probabilities. Selected controls use
  an accent, checkmarks and accessible pressed states, with brighter secondary text and focus rings.
- Saved slips retain their original selection details and first successful payout illustration.
  Changed or unavailable quotes stay reviewable and removable instead of disappearing, and
  each market's slip is restored when returning to it. Historical live grading remains unavailable.
- Record leads with per-model performance, sample sizes, game-day coverage and fee assumptions.
  Audit details are expandable; an invalid record still raises a warning above the results.
- Validation: all 1,426 Python tests passed (3 expected failures). Front-end interaction tests,
  lint and the production build passed. The running app, health, board and record endpoints
  returned HTTP 200; the NBA board returned seven simultaneous live games with receipt times.

### Reliable slips and clearer information
- Streamlit's live caches store plain values and reconstruct game records when read,
  preventing serialization errors from dataclass instances left over during a code reload.
- The shared live feed now checks scheduled games against their individual box-score status
  in parallel. A delayed aggregate scoreboard can no longer hold a game in pregame when its
  own feed confirms it has started. A failed feed for one game leaves the others available;
  scheduled time alone never marks a game live. Applies to both React and Streamlit.
- Web selections now use deterministic quote IDs rather than table positions. Adding or
  reordering lines cannot turn a saved selection into another bet; a changed price or blended
  probability invalidates the old quote. Older positional browser slips are deliberately not
  restored, with a migration explanation in the Parlay screen.
- Slip calculations are bound to the exact market, selections and stake. Pending or failed
  requests cannot display a previous payout, including in the mobile bar.
- Live tracking rejects slips outside today's Eastern game day rather than matching an old
  selection to a new game with the same teams. Historical live tracking remains unavailable.
- A Kalshi-only ledger no longer hides the Record screen. FanDuel model summaries remain
  explicitly separate from the other-source breakdowns.
- The web app uses descriptive model names (Recent average, Minutes, Context, Shot profile),
  shows market/model/blended probabilities together, explains the 30/70 blend, and labels
  multiplied-price payouts as illustrations rather than executable quotes. Kalshi fees are
  explicitly excluded; the underlying pricing and prediction models are unchanged.
- Added a recorded-board refresh action and load time, retry feedback, and periodic job-health
  refresh. The board explains that recorded prices are not live executable prices.
- Added regression coverage for stable selection identity, changed quotes, old-game tracking,
  Kalshi-only records and delayed/failed front-end slip pricing. Front-end tests now run in CI.
- Validation: 1,424 Python tests passed (3 expected failures), both front-end tests passed,
  and front-end lint and production build passed. A Streamlit runtime smoke test loaded
  the real scoreboard, box score and game details without serialization errors; the feed
  reported three simultaneous live games. Independent start recovery is covered by simulation.

### A Steady list on the Parlay screen
- **Steady** (`api/service.py` `steady_for`, `web/src/screens/Parlay.tsx`): tonight's legs a
  player reached in 18+ of his last 20 games, one per player and stat (the highest number that
  still qualifies), each shown next to what it costs. A convenience for building slips, not an
  edge: the season backtest found these hit 87% of the time at an 88-cent price.

### A full-season test against Kalshi
- **Kalshi's archive** (`data/kalshi_history.py`, `scripts/kalshi_history_download.py`): every
  settled 2025-26 player-points market and its hourly prices, free and keyless, cached and
  resumable. Tip-off comes from NBA's official schedule (Kalshi's own time agrees on 99% of
  markets; the rest are dropped); the price is the last hourly bid and ask that closed 15+
  minutes before tip; markets that settled at a price (a player who never played) are left out.
- **The backtest** (`scripts/nba_kalshi_backtest.py`, report in `docs/KALSHI_BACKTEST.md`):
  13,443 markets on 136 nights, with walk-forward projections (trained on 2023-24 and
  2024-25) and role correction curves refitted on 2024-25 alone, since the production curves
  were fitted on 2025-26. Accuracy and betting results come with 95% intervals from
  resampling whole nights.
- **What it found:** every model alone is less accurate than Kalshi; blended 30/70 with Kalshi
  they are slightly more accurate than Kalshi alone; and no betting rule makes money once
  Kalshi's spread and fee are paid. Betting every 2%+ value rung lost (Simple -12%, mostly on
  long shots); with the guardrails the results are near break-even with wide intervals. The
  role correction barely moves accuracy.
- **Did the edge last?** The report now scores each half of the season. The blend's small lead
  over Kalshi is all from before January 28, when these markets were new; after that the blend
  and Kalshi are tied. Tuning the spread, the blend weight or a stacked model on the early half
  made the late half worse, so the 30/70 blend and the recording rules are unchanged.
- **Are consistent players easy locks?** Markets grouped by how often the player reached the
  number in his last 20 games. The steadiest (90%+) hit 87% of the time at an average ask of
  88 cents: the cheapest bets to make (-2%), still not a profit. A nightly three-leg slip of
  them won 74% at an average cost of 77 cents.
- CI actions moved to their Node 24 versions (checkout v5, setup-python v6, setup-node v5).

### A real web app
- **FastAPI service** (`src/edgefinder/api`) over the same Python the Streamlit app uses, so
  the two can't disagree: `/api/board`, `/api/ideas` and `/api/slip` for the Parlay screen,
  `/api/live`, `/api/live/{game}` and `/api/live/track` for Live, `/api/players`, `/api/picks`
  and `/api/record`. Short caches keep a page of taps from re-reading files, and NBA's live
  feed is read at most every 8 seconds however many people are watching. Documented at
  `/api/docs`.
- **React, TypeScript and Tailwind front end** (`web/`), built by Vite and served by the same
  server on one port. Five screens:
  - **Parlay:** the props list (pick a number on a sideways strip, then Yes or No), price gaps
    and suggested slips. The slip is priced as you build it; it sits beside the props on a wide
    screen and is a bottom bar on a phone, and it survives a reload.
  - **Live:** a score strip of every game, a header in both teams' colors with timeouts, fouls
    and the bonus, the score popping when it changes, the shot chart on the home team's floor,
    team stats, leaders, the play-by-play (new plays flash in) and the box score. Your slip is
    tracked bet by bet. It all refreshes every 10 seconds and pauses while the tab is hidden.
  - **Players:** a search that ignores accents, the season at a glance, tonight's line, and how
    often the player has cleared any number (the hit rate updates as the line moves).
  - **Picks:** what each model would bet, and every line with each model's projection.
  - **Record:** the tamper log, each model's record and calibration, running profit, the record
    split by price source and stat, closing-line value, and every pick as locked.
- **Tests:** the API is covered against a made-up ledger and live feed (no files, no network),
  including a check that the server never hands out files outside the built app.

### Fixes
- **Live slip tracking counted points for every bet.** A rebounds, assists or 3-pointers bet
  was judged on the player's points. Each bet now counts its own stat, and the progress text
  says which ("6 rebounds so far, needs 4 more").
- **Kalshi picks now pass the same guardrails as X+ picks:** the model must give the side at
  least 35% and sit within 15 points of Kalshi's price. Kalshi's ladders price every rung, and
  most early Kalshi picks were long shots far out on them. On the 177 Kalshi picks already
  graded, the rule would have dropped 103 that went 14-89 (-63.1 units) and kept 74 that went
  35-39 (-0.7). That was measured on the same picks that prompted the change, so it is not an
  independent test. Picks already locked are unchanged; FanDuel picks are unaffected.

### Honest chances by player role
- **Measured** (`scripts/nba_calibration_by_line.py`, 2025-26, never seen in training): when the
  older models gave a bench player (under 18 minutes) a 70%+ chance, it came true about 70% of
  the time, not the 83% they said; rotation players were about 6 points too high; starters were
  honest. `context-v2` was close already.
- **Corrected** (`models/nba_recalibration.py`, fitted by `scripts/nba_recalibration_fit.py`):
  a curve per model and role from what the model said to what happened, fitted on 2024-25 and
  checked once on 2025-26 (bench locks: said 84%, corrected to 72%, happened 71%). The Parlay
  builder prices points legs with the corrected chance; the ledger keeps each model's raw
  numbers, so the record still judges the models as they are.
- **Bench players' locks are no longer suggested** in slips (they can still be added by hand).

### A cleaner app
- **An app shell:** a top bar with the logo, the name and status chips (games live now, when
  lines were last checked), pill navigation with the open view in white, and Streamlit's own
  header hidden. All six views fit one row on a phone.
- **Parlay:** Game day, Prices and Model on one row, days as "Yesterday" or "Wed, Nov 4", a
  summary strip (games, player props, price gaps, prices from), no empty slip bar, and "How
  this works" moved to the bottom.
- **The court, redrawn** as a drawing that keeps its shape at any width: a dark floor glowing in
  the home team's color, the paint and center circle in that color, the logo at center court,
  makes as dots and misses as crosses, new shots popping in, and each team shown at its own end
  (second-half shots are turned around, the way game apps do it). Team names in the Team stats
  header no longer show stray asterisks.
- **Picks:** honest wording (several nights are being graded; a projection far from the line
  usually means missing news), friendly dates and short team codes.

### The price gaps get a record of their own
- **Logged before tip-off.** Each snapshot that records prices writes that night's
  FanDuel-vs-Kalshi gaps to `data/price_gap_log.csv`: one row per bet, at the first price seen,
  and never once its game has started, so a gap can't be called after the fact or improved later.
- **Graded each morning** by the settle job at a flat 1 unit (over beats the line, under stays
  below it, "25+" needs at least 25; a player who didn't play is a void) and reported there.
- **On the Record tab:** "Betting the price gaps" shows gaps logged, the record and units, split
  into exact matches and ones estimated from Kalshi's ladder.
- It starts with the next slate. Last night's gaps are not back-filled: they were found after
  tip-off, which the rule forbids.

### Where FanDuel and Kalshi disagree
- **A price-gap flag** (`tracking/price_gaps.py`) on the Parlay screen: bets one market prices
  well above the other's fair chance for the same thing, biggest first, with an Add button.
  The gap is the expected profit per $1 IF the other market is right (at least 3%; anything
  over 30% is treated as a stale price and dropped).
- **How bets are matched:** FanDuel's X+ ladder and Kalshi's contracts line up exactly on the
  same number; FanDuel's main over/under is compared exactly when it sits on a Kalshi number, and
  otherwise priced from a curve fitted to the player's Kalshi ladder, labelled "est.". It also
  works the other way (Kalshi paying more than FanDuel's fair chance), noting Kalshi's fees.
- **No model of ours involved**: it uses the other market as the reference, after "Beating the
  bookies with their own numbers" (Kaunitz et al., 2017).
- First night (2026-11-05): 7 gaps, 3 won, about break-even at a flat stake. Far too few to judge.

### A cleaner Live screen
- **Score strip.** Every game is one chip with its live score ("MIA 87-103 GSW · Q4 7:25"),
  games on now first. Tap one to open it. The separate card list that repeated each game is gone.
- **Game header.** The open game is shown big: both logos and scores in the teams' colors, the
  clock in the middle, timeouts, team fouls and the bonus under each team, the leader in white,
  and a "+2" / "+3" that floats up when a team scores. Players in foul trouble are listed below.
- **One score everywhere.** The scoreboard feed trails the play-by-play by a minute or more, so
  every live game now takes its score and clock from the latest play; the chip and the header
  can no longer disagree.
- **Less clutter.** The slip section appears only when there is a slip.
- **Refreshes every 10 seconds** (was 30), with the feeds at most 8 seconds old.
- **More motion, only on change.** New plays slide in and glow on the team's color, a slip leg
  glows when it flips (alive to hit, say), the LIVE badge pulses, and cards lift on hover.
  Nothing replays on a plain refresh, and all of it is off for people who prefer reduced motion.
- Checked during Heat at Warriors: the page refreshed by itself, the score and clock moved, and
  the "+2" appeared when Miami scored.

### Repo cleanup, license, CI and a new README
- **Removed the old multi-sport code**: the MLB board, soccer, UFC, bet evaluator, bet log
  and old parlay views and the pipelines, models and clients behind them (20 modules, 3
  scripts and about eighty tests that covered only them). The live app no longer imports
  any of it, and `ui/shared.py` is down to the one helper it used. It remains in git history.
  The question-box logic (`tracking/nba_questions.py`) stays: it is built and tested and
  waiting for a screen.
- **License: PolyForm Noncommercial 1.0.0** (`LICENSE`): free to read, run and learn from,
  not for commercial use.
- **CI:** a GitHub Actions workflow runs the tests on Windows, with a badge in the README.
- **README rewritten** to match what the project is: screenshots (with neutral images in place
  of NBA photos and logos), the live record as an honest table from `scripts/readme_results.py`,
  an architecture diagram, how to verify the record, and a data and licensing note.

### A tamper-evident record
- **Append-only pick log with a hash chain** (`tracking/pick_chain.py`). Every ledger row and
  every result is also written to `data/nba_paper_log.chain.jsonl`, each entry fingerprinted
  together with the one before it. The 659 rows and 154 results already in the ledger were
  imported once and are marked as such.
- **Audit on the Record tab.** "Has anything been changed?" shows whether the log is intact,
  how many ledger rows match it, and the latest fingerprint, and warns if a published
  fingerprint no longer matches. Edited, deleted and never-logged rows are named.
- **Publishing.** `python scripts/verify_record.py --write-digest` adds the day's fingerprint
  to `record/DIGESTS.md`; committing and pushing it gives an independent timestamp.
- **Safe to fail.** Chain problems are logged and never stop a snapshot or a settle; a row it
  misses shows up in the audit as never logged.

### Game filter, a faster slip search, and phone polish
- **Filter the Parlay tab by game.** The Game chips sit above the suggested slips and filter
  both them and the prop list. Choosing one game gives same-game slips (different players,
  priced with the measured correlations); "All games" gives one leg per game as before.
- **Much faster slip search.** The search ranks slips with a quick probability calculation
  (about 400x faster, within 1e-5) and prices only the few shown exactly, skips slips that
  cannot meet the payout or chance bar before the slow part, and remembers results between
  taps. A same-game search that took up to 31 seconds now takes under 2.
- **Snapshot retries.** A blip on the odds service (such as a 502) is retried up to three
  times, 20 seconds apart, before the run is counted as failed.
- **Phone layout** (from the mobile audit): all six tabs fit one row, every tap target is at
  least 44px, and alert boxes keep the black look.

### Reliability, closing-line value and cross-stat correlations
- **Job heartbeats.** The snapshot and grading jobs write when they last ran and how it went
  (`data/job_heartbeat.json`). The app shows "Lines last checked ..." in the footer and a
  notice at the top when snapshots are behind or stopped, or when a run failed. Snapshot
  tasks now also wake the PC to run (`WakeToRun`).
- **No pick after tip-off.** `build_ledger_rows` and the X+ builder refuse any price taken at
  or after the game's start, so the "recorded before the game" claim is enforced in code, not
  just counted. (Found by the record audit.)
- **Closing-line value for Kalshi.** The late snapshot now also saves Kalshi's prices
  (`data/kalshi_snapshots.csv`); grading uses the latest one as the closing price for a
  Kalshi pick on the same line. The Record tab opens with "Did the price move our way?":
  average move, share of picks that beat the close and how many were measured, per source.
- **Different stats, measured.** Same-game correlations between stats, from three seasons of
  logs. Between different players they are near zero (largest: a teammate's assists with
  another's points, +0.08). The same player's own stats are strongly linked: points and
  threes +0.72, points and rebounds +0.26, rebounds and assists +0.18, points and assists
  +0.13. The slip maths uses them, and one player can now be on a slip once per stat.

### A livelier live screen
- **Points pop.** When a team scores between refreshes, its score flashes green and a
  "+2" or "+3" floats up beside it, on the scoreboard and on the open game. Nothing pops
  on first load, and the animation is switched off for people who prefer reduced motion.
- **The home team's court.** The shot chart now sits on the home team's floor: their color
  as a wash across the court and their logo at center court.
- **Fouls.** Under the timeouts, each team's fouls and the players in foul trouble
  (four or more). The box score has a PF column.

### Every stat, FanDuel or Kalshi, and a sportsbook-style list
- **One page, every stat.** There is no market to pick. Points, Rebounds, Assists and
  3-pointers are stacked sections you open and close (Points open first), and one slip
  can mix them. Chips choose the Game day, Prices (FanDuel, Kalshi) and Model, offering
  only what has prices that day. A stat the chosen model didn't price uses the Simple one. Kalshi shows a one-line note that its prices are before fees and its
  markets are thin (only liquid markets are ever recorded). A slip is cleared when
  you change any chip.
- **All props, one scroll.** The bet list shows every game's props in one page with a
  header per game, and no inner scroll box. The game chips are an optional filter.
  A player with many lines (Kalshi) shows his most even line first and the rest
  under "More". Averages beside each player follow the chosen stat.
- **List view, like Kalshi.** Each player is a row: the market's chance for the step you
  pick (the model's number underneath), a stepper of "at least" choices (20+ 25+ 30+),
  and Yes / No prices (cents on Kalshi, American odds on FanDuel). It is the default on
  Kalshi, with the old Grid as the other choice.
- **Plumbing:** `nba_parlay.candidate_legs` takes `stat` and `book`, `sources` says
  what has prices for a day, `main_line` picks the line to feature, and `ladder` turns a
  player's lines into steps.

### A fourth model, `context-v2`
- **Runs alongside the others** (the nightly snapshot prices every line with it too,
  including Kalshi points lines). Shot-habit inputs, a blend of the direct and
  minutes-based views, and probability spread sized to each player's projection.
- **Measured on 2025-26 after choosing on 2024-25:** points error 5.108 -> 5.090
  (small but real); log score -3.302 -> -3.234 from the variable spread (the big
  gain, since low and high projections were priced with the wrong width).
- **Plumbing:** `negbin.varying` makes a spread that depends on the projection, and
  the ledger, X+ and Kalshi pricing accept it. `nba_shot_features` holds the new
  inputs. The v1 projector is unchanged apart from two small hooks v2 reuses.
- **Not a promise of profit.** This is better probabilities, measured on past games;
  whether it beats FanDuel is what the live record is for.

### Slips worth the stake, averages, and a model experiment
- **Suggested slips must pay.** Each style has a minimum win per $1 (Safer $1.00,
  Balanced $2.00, Bigger payouts $6.00) and every slip needs at least one real leg
  (about -200 or better), so a slip of only locks is never offered. When nothing
  qualifies, the screen says so.
- **Player averages on bets.** The bet list and idea cards show each player's
  season average and last-10 average beside the line.
- **Model experiment (`scripts/nba_improve_eval.py`).** Chosen on 2024-25, scored
  once on 2025-26: shot-attempt features and a blend with the minutes model cut
  points error by about 0.4% (real, small). Letting the probability width depend on
  the size of the projection improved the log score about five times as much.

### Locks on slips, and no stray blue
- **Safe "lock" legs may join a slip.** A suggested leg can now cost up to about
  -1000 (it was about -333), as long as it is still worth betting on its own.
  Nearly certain padding legs (about -2000) stay out.
- **No leftover blue:** links, info boxes and the Record tab's profit chart now
  follow the black palette.

### Record views count FanDuel only
- **Kalshi rows can't pollute the record.** The Record, Players, Picks and Parlay
  screens now read `nba_paper.load_fanduel_ledger()`, so once Kalshi prices land
  in the ledger they are never counted in the per-model FanDuel record or
  accuracy scores.
- **Four small fixes:** a pick locked seconds before tip is no longer flagged
  "after tip-off", a 96% chance no longer reads "10 in 10", a sub-cent loss shows
  `$0.00` rather than `-$0.00`, and the first accuracy bin reads "0-20%".

### Black look, like X
- **New look:** pure black, hairline dividers, white pill buttons, white accent
  instead of blue, status colours kept (green hit, amber alive, red missed).
  The CSS moved to its own file, `ui/theme.py`.
- **Less text on the Parlay screen:** one-word model chips (Simple, Smarter,
  Smartest), the explanations collapsed into one "How this works" section,
  and suggested slips shown as cards (player photo, bet, odds, chance and
  payout) instead of a run-on line.

### Kalshi prediction-market prices (data client only)
- **New `edgefinder.data.kalshi`**: reads Kalshi's public market data (no
  account or key) for player points, rebounds, assists and 3-pointers.
  Each "35+ points" contract becomes a row with the player, game, threshold,
  yes/no bid and ask, spread and volume, and an `is_liquid` flag (both sides
  quoted, spread at most 10 cents, at least 25 contracts traded).
- **Priced like a prop line.** "N+" becomes an over at N - 0.5 at the yes
  ask, and the no side becomes the under at the no ask, in the same shape the
  FanDuel parser produces, tagged `book="kalshi"`.
- **Prices are before Kalshi's trading fees**, and books are often thin and
  wide (a 5-cent bid against a 33-cent ask is normal), so treat them as
  indications, not as prices you can trade at.
- Not wired into the app yet; nothing changes on screen.

### Kalshi prices in the paper ledger
- **The snapshot job now records Kalshi too.** For each game taking its early
  snapshot (the same 150-240 minutes before tip-off window as FanDuel, no new
  timing), liquid Kalshi contracts for points, rebounds, assists and 3-pointers
  are written to the ledger with `book="kalshi"` and the right `stat`, so they
  can be graded and bet-built later. New module
  `edgefinder.tracking.nba_kalshi_ledger`.
- **Joined to the game by teams and date.** A Kalshi ticker names the away and
  home tricodes and the date; it joins the scheduled game with those teams on
  that Eastern date. A code that matches no scheduled team is skipped and
  logged, never guessed. Thin or one-sided books (`is_liquid` false) are not
  recorded.
- **Safe to re-run, safe to fail.** The ledger key is (game, player, line,
  model, stat, book), so a repeat run adds nothing and the early price stands.
  Kalshi is fetched once per series after the FanDuel work; if it fails, one
  warning line is logged and FanDuel is untouched. It costs no Odds API
  requests, so the request reserve does not apply to it.
- **Rolling-average model on all four stats**, using each stat's own
  dispersion; the points-only models also price Kalshi points. Kalshi prices
  are before trading fees, so Kalshi pick EVs flatter the bettor.
- **Parlay legs stay FanDuel points.** The over/under leg builder now ignores
  other books and stats in the shared ledger.

### Plain-English stat questions (logic only, no screen yet)
- New `tracking/nba_questions.py` answers questions like "How often has
  Brunson scored over 24 in his last 10?", "Did Jokic get 10+ rebounds this
  season?" and "Brown points under 19.5 at home". Code counts the games; there
  is no language model, and an answer is never guessed.
- Questions become a `Query` (player, stat, over/under/at-least/at-most, line,
  last N games or this season, home/away) that a future language-model parser
  could also produce. Anything unclear gets a message saying what was missing
  or ambiguous: "Johnson" asks which Johnson, a misspelling offers suggestions
  but is never answered, and opponents, averages, playoffs, other stats and
  predictions are refused with a list of what can be asked.
- "Over 24" means strictly more than 24; "24+" and "at least 24" include it. A
  whole-number line landed on exactly is a push, neither over nor under, the
  same as the player lookup's hit rate.
- Numbers must be digits ("20", not "twenty"). No window means this season,
  and there is no quiet fall-back to last season.

### Injuries and opponent context (a third model, `context-v1`)
- **Measured on past data first.** Following the same protocol as the minutes
  model (choose on 2024-25, score 2025-26 once), adding who's out, the
  opponent's defense and pace cut points error from 5.137 to 5.108 and
  improved how well the chances are calibrated. Real (95% interval +0.005 to
  +0.051 points) but small, about half a percent. Opponent and pace added
  almost nothing beyond the absences, and a direct points model without the
  context was slightly worse, so the gain comes from the new information.
- **Absences defined once, used two ways.** A team's recent roster is its last
  ten games' players; those who normally play 15+ minutes and aren't playing
  are "lost". Training reads that from past box scores; tonight it comes from
  ESPN's free injury report, using the same roster and definition.
- **Runs as a challenger**, priced on the same lines as the other two models
  and scored against them. It never replaces them until the record says so.
  If the injury report can't be fetched it carries on as if nobody is out.
- **Injury badges** in the bet browser (red OUT, orange DAY-TO-DAY) and a
  warning on the slip when someone on it is listed out. A real example came up
  immediately: a line was posted for a player who was later ruled out.
- **The pick-making snapshot moved later.** It used to happen at noon, before
  the injury report is published, so no model could know who was out. It is now
  taken 2.5 to 4 hours before tip-off. A downside: if the PC is off during a
  game's window, that game gets no early snapshot that night.
- New: `scripts/nba_context_eval.py`, which reproduces the numbers above.

### The public record page
- **Record tab:** every pick as it was locked, with the lock time and how
  long before tip-off, and a count of picks recorded at or after tip-off
  (shown in green when it is zero). It measures the "written down before the
  game" rule instead of asking anyone to trust it.
- **Per model:** record, units and return, plus a plain-language verdict that
  compares the model's accuracy to FanDuel's odds on the same lines, and
  refuses to judge until about 300 lines are graded. Even a good verdict says
  it still needs to hold up.
- **Running profit chart, a calibration view** (when it says 60%, does it
  happen 60% of the time?), a day-by-day table, and the full pick log. All
  show an honest empty state until the first games are graded.

### Suggested slips: fewer long shots
- Suggested slips now have a **risk style**: Safer (at least a 35% chance of
  hitting), Balanced (20%, the default) and Bigger payouts (8%). Before, they
  were ranked purely by expected profit, which put 1-in-37 long shots first.
- Slips no longer get **padded with near-certain legs** like "3+ points" that
  pay almost nothing and only add a leg. A suggested leg has to pay at least
  about -333.
- Each game now offers its likeliest worthwhile bet as well as its best-value
  one, so the cautious styles have something sensible to build from.

### Visual audit: cleaner, prettier, works on a phone
- **Team colors and logos everywhere they fit.** Players are shown as plain
  cutouts standing on the card, with no circle or backdrop behind them. Team
  identity comes from the colored edge of the card and the team logo beside
  the name. Game cards, the shot chart, the team comparison bars and the
  leader cards use team colors too, and two teams with similar colors (two
  greens, two reds) are automatically told apart. The colors are display
  values tuned for a dark background, not official brand colors.
- **Player pages** get a banner (the player standing on a wash of the team's
  color, with the logo and season) and big stat tiles.
- **Phone layout fixed.** The browse list used to explode each player into five
  stacked rows; it is now one compact row with pill-shaped over, under and X+
  buttons. The slip summary stays pinned to the top while you scroll, and the
  slip column stays in view beside the list on a wide screen. Found and fixed
  two CSS bugs on the way: phone rules placed above the base rules were being
  overridden, and sticky positioning needs to sit on the wrapper that can
  travel.
- **Cleaner chrome:** no sidebar, no Deploy bar, short tab names with proper
  icons that all fit on a phone. The responsible-gambling note and the
  Odds API count moved to a footer so they are still always visible.
- **Picks tab restyled** to match: bet cards instead of a table, a slim
  "untested" notice instead of a yellow warning box, chips instead of
  dropdowns, and a plainer title.
- **Less text up front** on the Parlay tab (the how-to and glossary are one
  collapsed section), and smaller headings on the in-app How it works page.

### Game center, modeled on how sports apps show a live game
- **Open any game** from the Live tab for Stats, Plays and Box score tabs
  under a score header with team logos, timeouts left and bonus status.
- **Quarter-by-quarter scores** and a **shot chart** on a full court: every
  make (dot) and miss (✕) for both teams at its real location, filterable by
  period, with each team's makes and attempts. The court is drawn to scale
  and tested (three-point arc distance, mirrored ends, hoop position).
- **Team stats side by side:** field goals, 3-pointers, free throws,
  rebounds, assists, steals, blocks, turnovers, points in the paint, fast
  break, second chance, points off turnovers, bench points and biggest lead,
  with the leading side highlighted (for turnovers, fewer leads).
- **Game leaders** and a full **box score** per team, starters and bench, with
  minutes, points, rebounds, assists, shooting splits, steals, blocks,
  turnovers and plus/minus.

### An easier slip
- **Slip stays in view:** browse on the left, the slip on the right, and a
  one-line summary with a Clear button at the top, so a bet is never out of
  sight after you add it.
- **One tap each way:** tap a price to add it (it gets a ✓), tap again to
  remove it, or hit the ✕ on any bet in the slip. A second price for the same
  player replaces the first.
- **One tap for a whole idea:** each suggested slip has an "Add to slip" button
  that loads all its bets at once.
- **Tappable chips instead of dropdowns** for the projection, the game to
  browse and the live game, and an in-app **How it works** page that shows
  the methodology and this changelog.

### Explaining it, and better player search
- **`docs/METHODOLOGY.md`:** how the predictions work, written to be said out
  loud. A 30-second version, a two-minute version with a worked example from
  real data, the details, the evidence so far (including that nothing has
  settled yet), what it can't do, and answers to the questions people ask.
- **Type-ahead player search:** the Players tab is now a dropdown that
  filters as you type, and it understands plain spellings, so "doncic" finds
  Dončić.

### Foundation for rebounds, assists and 3-pointers
- **One registry for four stats** (`models/nba_stat_model.py`): points,
  rebounds, assists and 3-pointers each know their game-log column, Odds
  API market, label and spread, and share one rolling-average projection.
- **Measured, not assumed:** each stat's spread and same-game correlations
  were fitted from three seasons of logs. Rebounds and assists turned out
  steadier than I had guessed (spread about 11 against 7.8 for points), and
  every same-game correlation is tiny (never above 0.04). Bets on different
  stats in one game are treated as independent, since nobody has measured
  that.
- **Ledger generalized:** rows now carry a `stat` and a `book`, a row's
  identity includes its line, and settlement reads the right box-score
  column per stat. Older ledger files are upgraded in place before any new
  row is written, so the header and rows can't disagree.

## 2026-11-04

### Sportsbook-style look, player lookup, and a logo
- **Look:** dark navy theme with blue accents, bet-slip cards with the
  player's photo and the price in a pill, and a highlighted slip summary.
  Inspired by betting apps' layout; no brand's name or logo is used.
- **Stake box:** type what you're betting and see what it wins, what comes
  back, and the average result at that stake. Nothing is placed or saved.
- **Tap to add:** pick a game, then tap over, under or X+ prices next to
  each player to add them to the slip, tap again to remove. A second price
  for the same player replaces the first. Changing the game day or
  projection now clears the slip instead of leaving stale picks.
- **Any game, with logos:** the Live view shows every game as a card with
  team logos, and any game can be opened for a play-by-play feed and box
  score. The header uses the freshest score from the feed, because NBA's
  scoreboard can trail its play-by-play.
- **Players tab:** search any player for photo, team, season averages, tonight's
  line and both projections, how often they've cleared a number (last 10
  and the season, for points, rebounds, assists or 3-pointers), a bar chart
  against that line, and recent games.
- **Logo:** `assets/logo.svg` and `assets/logo-mark.svg`, used in the app
  header, favicon and README.

### Live tracker
- **Live view:** your slip (whatever is picked in the parlay builder) with
  each bet marked hit, alive, missed, not started or void, a progress bar,
  and the player's photo; tonight's scoreboard; and any game's box score
  with who's on the court. Refreshes itself every 30 seconds from NBA's
  free live feed, with no key and no Odds API requests.
- **Settlement rules, tested:** an over or X+ bet is hit the moment the
  player reaches the target and stays hit; an under is missed the moment he
  reaches it and is only hit once the game ends below it; a player who
  never plays voids the bet and drops out of the slip instead of sinking it.

### Clearer parlay builder
- Plain language throughout: "Game day" and "Projection" instead of
  slate and model ids, a three-step how-to, and a glossary. Chances read as
  "1 in 37" or "9 in 10", payouts as dollars, and every slip gets a
  one-sentence verdict (wins, loses, or about break-even over time).
- Suggested slips are now "Ideas the model likes" and lead with the
  chance it hits, with a warning that long shots rank high on payout.
- A bar chart of each bet's chance next to the chance they all hit, and
  NBA headshots on every bet.
- Every bet says what stat it is ("points"), and legs carry a Stat field
  ready for rebounds and assists.

### Parlay builder
- **Parlay builder view:** pick over, under and X+ legs from the day's
  lines for either model and see the chance all hit, the break-even odds
  and the expected value. Each leg's chance is the model blended 30/70
  toward the market.
- **Same-game correlation, measured instead of assumed:** teammates'
  points correlate at -0.026 and opponents' at +0.023, consistent across
  three seasons (about 60,000 and 70,000 pairs). Same-game legs are
  priced with a Gaussian copula using those numbers; the effect on
  points-only slips is small, and the UI says so.
- **Suggested slips:** built only from legs worth betting on their own,
  with the same guardrails as X+ picks, one leg per game so legs are
  independent.
- `scripts/nba_correlation_report.py` reproduces the correlations.

### Ball Knowledge (rebrand)
- The project is now **Ball Knowledge**, basketball only. The dashboard
  shows just the NBA view; the MLB, soccer and UFC views, bet evaluator,
  parlay builder and bet log are no longer shown (their code is still in
  the repo).
- README rewritten around the product and a roadmap: evidence first,
  then injury data, a props parlay builder, and accounts and hosting.

### Added
- **NBA dashboard view:** suggested player-points bets, tonight's lines
  with both models side by side, scorecard and head-to-head, and a
  data-collection status panel. Read-only; never calls the Odds API.
- **X+ points bets** ("Jaylen Brown 15+"): a per-player ladder of each
  model's chance and break-even odds, plus a ledger of FanDuel's
  alternate-lines prices, priced by every model and settled from box
  scores. Recorded at the early snapshot for up to 4 games a night.
- **Pick guardrails for X+ prices:** a price is only a pick if the model
  gives it at least 35% and sits within 15 points of the market. Without
  this, long-shot tail prices produced fake edges.
- **Two models priced side by side:** `ewma-v1` (rolling average) and
  `minutes-v1` (learned minutes model times points per minute), each
  under its own `model_version`, so they are judged head to head on the
  same lines. One failing never stops the other.
- **Learned minutes model** with leak-proof pre-game features (rest,
  back-to-backs, games in the last 7 days, prior-season minutes, games
  missed). Offline it improved points MAE by about 1.4%.
- **NBA prop tracker:** budgeted FanDuel line snapshots (max 6 games a
  night, one early and one near tip-off, with a request reserve), a paper
  ledger, and settlement with closing-line value. Scheduled on Windows to
  run unattended.
- **NBA data layer:** season game logs with caching, rolling-average
  baselines, negative-binomial probabilities, and walk-forward scoring.
- **MLB:** Pinnacle sharp-consensus anchor, a leg-reuse cap for parlays,
  and a calibration backtest.

### Known gaps
- No injury or lineup data yet, which is the biggest remaining source of
  error in the minutes projection.
- Nothing has settled yet, so neither model has a record. The first
  results arrive on 2026-11-05.
- No NBA moneyline or spread. The parlay builder doesn't cover bets tied
  to a game's total or result, or FanDuel's own same-game slip price.

## 2026-08-21
- Initial EdgeFinder: MLB, soccer and UFC betting-value dashboard for
  FanDuel with Elo and Poisson models, Kelly stake sizing, a parlay
  builder, and a bet log with closing-line value.
