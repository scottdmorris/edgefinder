# Changelog

Newest first. Dates are when the work was committed.

## Unreleased

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
