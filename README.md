# Ball Knowledge

Basketball player projections and prop tracking, built to answer one
question honestly: does a points model add anything beyond FanDuel's own
price? Every projection is paper-tracked and scored against real results
before anyone is asked to trust it.

The plan is a product for building NBA parlays on top of those
projections. What exists today is the measurement engine and a read-only
dashboard; the parlay builder and accounts are next (see Roadmap).

## Quick start

```powershell
cd edgefinder
.venv\Scripts\streamlit run app.py
```

Runs at http://localhost:8501. The dashboard only reads files the
scheduled jobs write, so it works without an API key and never spends
Odds API requests itself.

### Live FanDuel lines

Get a free key at https://the-odds-api.com (500 requests/month) and put
it in `data/odds_api_key.txt` (git-ignored) or the `ODDS_API_KEY`
environment variable. The snapshot job (below) uses it.

## What's inside

The dashboard has one view, the NBA player-points tracker:

- **Suggested bets:** positive-expected-value player-points over/unders,
  best first, with how many models agree.
- **X+ points ("Jaylen Brown 15+"):** a ladder of each model's chance and
  break-even odds for any player, plus suggested X+ bets from FanDuel's
  alternate-lines market.
- **Lines and projections:** every line with both models' projections
  next to FanDuel's own devigged probability.
- **Scorecard:** each model's record and Brier score against the market's
  on every settled line, and a head-to-head on identical lines.

## How it works

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
injured tonight. One model failing never stops the other from recording.

**X+ points bets:** the models predict a whole distribution, so any total
can be priced. An X+ bet has no under side, so there is no devigged
market probability; the market anchor is the price's raw implied
probability, which is the conservative direction. Picks are limited to
prices where the model gives at least a 35% chance and sits within 15
points of the market, because out in the tail the model's spread is too
wide and small disagreements look like huge fake edges. Each X+ call
costs one request per game, so it runs for at most 4 games a night.

```powershell
.venv\Scripts\python scripts\nba_props_snapshot.py --dry-run  # what's due; spends nothing
.venv\Scripts\python scripts\nba_props_snapshot.py            # one snapshot cycle
.venv\Scripts\python scripts\nba_props_snapshot.py --backfill-models  # price archived pre-tip games with a new model
.venv\Scripts\python scripts\nba_props_settle.py              # grade picks, print the report
powershell -ExecutionPolicy Bypass -File scripts\install_nba_tasks.ps1  # schedule both
```

## Roadmap

1. **Evidence.** A few weeks of settled results decide whether either
   model beats the market. Nothing is sold until that's known.
2. **Injury and lineup data.** The biggest remaining lever on minutes.
3. **Parlay builder for props.** Legs from the same game are correlated
   (a blowout hurts every starter's minutes), so it has to price the
   combination, not multiply the legs.
4. **Accounts and hosting.** Needs a real database, a hosted scheduler,
   and a data licence that allows redistribution, since the free Odds API
   tier is for personal use.

## Earlier work

The MLB board, soccer and UFC views, bet evaluator, parlay builder and
bet log this project started as are no longer shown in the app. Their
code is still in the repo (`src/edgefinder/pipeline.py`, `models`, `ui`).

## An honest note on profit

Sportsbooks price parlays with compounding vig; most parlays are badly
-EV. The realistic path to profit is: bet only positive-EV singles a
model finds, size small, and judge the model by **CLV** (beating the
closing line), not short-term wins. If average CLV stays positive over
100+ bets, the edge is likely real; if not, the model needs work before
real money does. Never bet money you can't afford to lose.
Problem gambling help: 1-800-GAMBLER.

## Development

```powershell
.venv\Scripts\python -m pytest      # betting math, models, data layer, ledger
```

Layout: `src/edgefinder/betting` (odds/EV/parlay and negative-binomial
math), `models` (NBA baselines and the minutes model), `data` (NBA game
logs and The Odds API clients with file caching), `eval` (walk-forward
scoring), `tracking` (paper ledgers), `ui` (Streamlit views).
