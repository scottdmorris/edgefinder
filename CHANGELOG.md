# Changelog

Newest first. Dates are when the work was committed.

## Unreleased

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
