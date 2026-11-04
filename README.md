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
- NBA board activates when the season starts (same Elo engine, K=20,
  ~70-point home edge).

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
.venv\Scripts\python -m pytest      # 43 tests over the betting math
```

Layout: `src/edgefinder/betting` (odds/EV/parlay/Poisson math),
`models` (Elo, MLB, props), `data` (MLB Stats API + The Odds API
clients with file caching), `tracking` (bet log), `ui` (Streamlit
tabs), `pipeline.py` (board assembly).
