# Changelog

Newest first. Dates are when the work was committed.

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
