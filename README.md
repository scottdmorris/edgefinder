# EdgeFinder

A local dashboard that prices MLB (and, come October, NBA) bets against
FanDuel's lines and only recommends action when the model's price beats
the market's — with Kelly-based stake sizing and closing-line-value
tracking.

## Quick start

```powershell
cd edgefinder
.venv\Scripts\streamlit run app.py
```

Runs at http://localhost:8501. No API keys required to start.

### Optional: live FanDuel odds

Get a free key at https://the-odds-api.com (500 requests/month) and put
it in `data/odds_api_key.txt` (git-ignored) or the `ODDS_API_KEY`
environment variable. Without it, the board shows model predictions and
you enter FanDuel's odds manually in the Bet Evaluator.

## What's inside

| Tab | What it does |
|-----|--------------|
| Today's Board | Every MLB game with model win %, fair odds, model total, and (with an API key) EV vs FanDuel's actual lines, ranked best-first |
| Bet Evaluator | Price any moneyline, total, or pitcher-strikeout prop against the model; get EV and a quarter-Kelly stake |
| Parlay Builder | **Auto-suggests parlays from the day's data**: builds a pool of the strongest legs, combines them (never two legs from one game), and ranks combos by EV when FanDuel odds are loaded or by hit probability (with fair odds to compare against FanDuel's quote) without a key. If nothing clears +EV, it says so instead of forcing a ticket. Manual builder below shows true hit probability, fair vs quoted payout, and each leg's marginal EV |
| Bet Log | Real-bet P/L, ROI, and CLV — plus the **paper-trade record**: one click records the model's +EV picks (flat 1-unit stakes, no money), auto-settles them from final scores, and computes CLV from the line-history archive. This is the model's objective track record |
| Soccer | EPL, La Liga, Bundesliga, Serie A, Ligue 1: Poisson attack/defense model (trained on free football-data.co.uk results) vs FanDuel three-way and goals lines, market-anchored like MLB |
| UFC | FanDuel MMA lines with devigged market probabilities. Deliberately model-free (free MMA data is too thin to model honestly) — enter your own probability to price your read against the market |

Everywhere a bet can be logged there is a **custom stake input** showing
the dollar EV of your stake, with an overstake warning when you exceed
Kelly guidance. The sidebar shows your remaining Odds API quota, and
every odds refresh is archived to `data/line_history.csv` — powering
the board's line-movement view and closing-line capture for CLV.

## The model (v1)

- **Sharp anchor (Pinnacle)**: the odds fetch also pulls Pinnacle,
  the sharpest book on the API. When Pinnacle lists a game, its
  devigged price becomes the market anchor and the board shows a
  **Sharp edge** column — the EV of betting FanDuel's price against
  Pinnacle's probability, which needs no model at all and is the most
  trustworthy signal in the app. `scripts/backtest_mlb.py` runs a free
  walk-forward calibration backtest of the Elo model (2026 result:
  narrowly beats a home-advantage baseline, overconfident above 60% —
  which is why the model gets only 30% weight).
- **Market anchoring**: for EV and suggestions, model probabilities
  are blended 30/70 toward the devigged anchor price — the market
  embeds injuries, lineups, and weather the model can't see, so raw
  model edges of 20%+ are treated as data problems, not free money.
  Games where model and market disagree by >15 points are flagged ⚠️
  and excluded from suggestions. In-play odds are filtered out and
  odds events are matched to games by start time (series/doubleheader
  safe). Raise `MODEL_WEIGHT` in `pipeline.py` only after CLV tracking
  proves the model beats closing lines.

- **Win probability**: Elo ratings trained on the season's completed
  games (K=4, 24-point home edge), shifted by the starting-pitcher ERA
  matchup (capped logit adjustment).
- **Totals**: expected runs from each side's scored/allowed rates plus
  an opposing-starter ERA nudge; over/under probabilities from a
  Poisson distribution.
- **Strikeout props**: recency-weighted K/start over the last 10
  starts, scaled by the opponent's strikeout-proneness (capped ±15%).

### Known simplifications (roadmap)

- Runs are over-dispersed vs. Poisson; a negative-binomial total would
  be sharper.
- No park factors, bullpen strength, lineup, or rest-day inputs yet.
- Parlay legs are assumed independent — same-game parlays are
  correlated and the builder warns about this.
- The NBA game board (Elo, K=20, ~70-point home edge) isn't built yet;
  the NBA work so far is the player-prop tracker below.

## NBA player-prop tracking (paper only)

A measurement pipeline for NBA player-points props, built to answer one
question honestly: does a points model add anything beyond FanDuel's own
price?

- **Baselines first.** `scripts/nba_baseline_eval.py` scores four
  rolling-average predictors walk-forward over a full season (points MAE
  is about 5.2 for all of them). Every prediction uses only earlier
  games, which the tests enforce.
- **Budgeted line snapshots.** The free Odds API tier is 500 requests a
  month and a props call costs one request per game, so
  `nba_snapshot_plan` covers at most 6 games a night: one early snapshot
  (the price a pick is made at) and one inside 90 minutes of tip-off (a
  closing-line proxy). A reserve stops it before the quota runs dry, and
  re-running never spends twice on the same job.
- **Paper ledger.** Every priced line is logged with the model's
  probability and the market's devigged probability, so calibration is
  scored on all lines, not only the picks. Settlement grades picks at a
  flat 1 unit, voids players who don't play, and attaches closing-line
  movement.
- **The test.** `scripts/nba_props_settle.py` compares the model's Brier
  score with the market's on every settled line. If the model can't beat
  the market's own number, it has nothing to offer.

Two models price every line side by side, each under its own
`model_version`: `ewma-v1` (a rolling average of points) and
`minutes-v1` (a learned minutes model times recent points per minute;
see `scripts/nba_minutes_eval.py`). Offline, minutes-v1 beat the rolling
average by only about 1.4% (points MAE 5.21 to 5.14, 95% CI 0.054 to
0.095) while perfect minutes would give about 16%, so most of the
remaining error is information nobody has before tip-off, like who is
injured tonight. The settle report scores each model and compares them
head to head on the lines both priced. One model failing never stops
the other from recording.

```powershell
.venv\Scripts\python scripts\nba_props_snapshot.py --dry-run  # what's due; spends nothing
.venv\Scripts\python scripts\nba_props_snapshot.py            # one snapshot cycle
.venv\Scripts\python scripts\nba_props_snapshot.py --backfill-models  # price archived pre-tip games with a new model
.venv\Scripts\python scripts\nba_props_settle.py              # grade picks, print the report
powershell -ExecutionPolicy Bypass -File scripts\install_nba_tasks.ps1  # schedule both
```

## An honest note on profit

Sportsbooks price parlays with compounding vig; most parlays are badly
-EV and the builder will show you exactly how much. The realistic path
to profit is: bet only positive-EV singles the model finds, size with
fractional Kelly, and judge the model by **CLV** (beating the closing
line), not short-term wins. If average CLV stays positive over 100+
bets, the edge is likely real; if not, the model needs work before
real money does. Never bet money you can't afford to lose.
Problem gambling help: 1-800-GAMBLER.

## Development

```powershell
.venv\Scripts\python -m pytest      # betting math, models, data layer, ledger
```

Layout: `src/edgefinder/betting` (odds/EV/parlay/Poisson and
negative-binomial math), `models` (Elo, MLB, props, NBA baselines),
`data` (MLB Stats API, NBA game logs, The Odds API clients with file
caching), `eval` (walk-forward scoring), `tracking` (bet log, paper
ledgers), `ui` (Streamlit tabs), `pipeline.py` (board assembly).
