# How Ball Knowledge predicts player stats

Written to be explained out loud. Read the first section for a 30-second
answer, the second for two minutes, and the rest when someone asks "but how
does that part work?" Every number here comes from the code or from a test
run; where something has not been proven yet, it says so.

## In 30 seconds

For each player in each game, we predict how many points (and rebounds,
assists, 3-pointers) he'll get, turn that prediction into the chance of going
over any number, and compare it to what the sportsbook's price implies. Then
we keep score in public: every pick is locked before the game and graded
afterwards, so the models have to earn trust instead of asking for it.

The honest headline: the models are simple statistics, not magic. Their
value so far is measurement discipline, and the question we're testing is
whether they add anything beyond the sportsbook's own price.

## In two minutes

```
 game logs ──► projection ──► chance of over/under ──► blend with market ──► pick? ──► graded
 (free)        two models     negative-binomial curve   30% model, 70% book    EV ≥ 2%    vs the book
```

**1. History in.** Every player's past games: points, rebounds, assists,
3-pointers and minutes, from NBA's own stats feed.

**2. Two projections, same slot.**
- **`ewma-v1`, the baseline.** A weighted average of recent games, where
  recent ones count most and older ones fade. At the start of a season it
  leans on last season.
- **`minutes-v1`, the learned model.** Points = minutes × points per
  minute. A machine-learning model predicts the *minutes* from rest days,
  back-to-backs, workload and recent absences; we multiply by his recent
  scoring rate.

**3. One number to a chance.** A player doesn't score exactly 24.4; he lands
anywhere from 10 to 40. We use a standard curve for count data (a negative
binomial, with its spread fitted from past misses) to turn "expect 24.4"
into "chance of 25 or more".

**4. Compare with the market.** A sportsbook's price, with its built-in cut
removed, is its own estimate of the same chance. We blend **30% model, 70%
market** (the raw models are overconfident) and calculate expected value:
chance × payout − 1. A bet needs at least +2% to count as a pick.

**5. Keep score.** Picks are recorded before the game and graded after it.
The test that matters: does the model's accuracy (Brier score) beat the
market's on the same lines?

### A real example

Jalen Brunson, points line **24.5**, over at **−106** (FanDuel, 2026-11-04):

| Step | Number |
|---|---|
| `minutes-v1` projection | 24.4 points |
| Model's chance of 25+ | 44.8% |
| FanDuel's own chance (cut removed) | 48.1% |
| Blended, 30% model + 70% market | 47.1% |
| Payout at −106 | 1.94× |
| Expected value | 0.471 × 1.94 − 1 ≈ **−8%** |

Result: not a pick. The model is *less* bullish than the book, so there is
nothing to bet. Most lines end like this, which is the point: the system's
default answer is "no edge here".

## The details

### Data
| What | Where | Notes |
|---|---|---|
| Player game logs | `nba_api` (NBA stats site) | Free; the training and grading data |
| FanDuel lines | The Odds API | Free tier is 500 requests a month, so snapshots are budgeted |
| Live scores, box scores | NBA's live feed | Free; used by the Live tab |

Lines are snapshotted at most twice per game: once early (the price a pick is
made at) and once near tip-off (a stand-in for the closing line).

### Leak-free by construction
A prediction for a game uses only games played strictly before it. The
game's own result can never feed its own prediction. Tests enforce this, and
upcoming games are predicted through a placeholder row so no future data can
sneak in. This is the most common way sports models fool their builders, so
it's tested rather than trusted.

### Model 1: the rolling average (`ewma-v1`)
An exponentially weighted moving average of the stat (weight 0.15 per game,
so roughly the last six or seven games dominate). Early in a season it is
shrunk toward last season's average. Four rolling baselines were scored
walk-forward over a full season and landed within a few hundredths of each
other (points error about 5.2); this is the one in use.

### Model 2: minutes × rate (`minutes-v1`)
- **Minutes model.** A gradient-boosted decision-tree regressor
  (scikit-learn; 200 shallow trees, depth 4, learning rate 0.05, trained on
  the last three seasons). It uses 14 inputs: how his minutes have trended
  (fast, medium and slow averages, last game, last three, volatility), his
  season and prior-season minutes, rest days, back-to-back, games in the last
  seven days, home or away, and how many of his team's last ten games he
  missed.
- **Rate.** His recent points per minute (a weighted average, so a hot
  stretch counts but doesn't dominate).
- **Projection** = predicted minutes × rate.

Why bother? Most of a player's game-to-game swing is minutes, not shooting.

### From a projection to a chance
A negative binomial distribution with the projection as its mean. Its spread
("dispersion") is fitted from past misses with a method-of-moments estimate,
separately per stat:

| Stat | Dispersion | Reads as |
|---|---|---|
| 3-pointers | 6.8 | the widest swings, streaky |
| Points | 7.8 | wide |
| Rebounds | 10.7 | steadier |
| Assists | 11.3 | the steadiest |

(A lower number means more spread around the projection.)

Whole-number lines exclude the push, so a line of 20 and 20.5 are the same
bet.

### Blending with the market
`used chance = 0.30 × model + 0.70 × market`, where the market chance is the
price with the bookmaker's cut removed. The 30% weight is deliberately low
and can be raised only if the track record earns it. A pick needs expected
value of at least 2%.

Extra guardrails on "25+"-style bets, because the model's spread is fitted
near the middle of the distribution and gets unreliable in the tails: the
model must give the bet at least a 35% chance, and must sit within 15
points of the market. Without these, long shots produced fake edges of 50%+.

### Parlays
Chances multiply, with one correction: two bets from the same game aren't
independent. We measured how much players' results move together from three
seasons of game logs (for points, about 60,000 teammate pairs and 70,000
opposing pairs; the other stats use tens of thousands each) and priced
same-game legs with a Gaussian copula:

| Stat | Teammates | Opponents |
|---|---|---|
| Points | −0.026 | +0.023 |
| Rebounds | −0.005 | +0.023 |
| Assists | −0.025 | +0.014 |
| 3-pointers | −0.002 | +0.004 |

**Which slips get suggested.** Only bets that are each worth making on their
own, one per game so they're independent, and only slips with a real chance
of hitting: at least 35% for "Safer", 20% for "Balanced" (the default) and 8%
for "Bigger payouts". Near-certain legs like "3+ points" are excluded, since
they pay almost nothing and just pad a slip.

All small, consistent across seasons, so for player stats alone, treating
legs as independent is nearly right. Bets on different stats are treated as
independent because that hasn't been measured.

### Grading
Every priced line is logged, not just picks, so accuracy is scored on all of
them. Picks are graded at a flat one unit; players who never play are
voided. The main test is each model's **Brier score against the market's**
on the same lines (lower is better). If the model can't beat the market's own
number, it has nothing to offer.

## Evidence so far

**Offline (past data, walk-forward, no peeking):**
- The learned minutes model beat the rolling average by about **1.4%** on
  points error (5.21 → 5.14), with a 95% confidence interval of 0.054 to
  0.095 points. Real, but small.
- It was closer in only 51.8% of player-games, so it is a slight edge, not a
  dominant one.
- With *perfect* minutes the error would drop about 16%, so most of what's
  left is information nobody has before tip-off, chiefly who is injured.

**Live (paper tracking):** the tracker started on 2026-11-04 and nothing has
settled yet. There is no live track record to report, and we say so. The
first results land on 2026-11-05.

## What it does not do
- **No injury or lineup information.** The biggest single gap. A star ruled
  out changes every teammate's night.
- **No opponent information.** Nothing about the other team's defense or
  pace; the minutes model knows home or away but not who the opponent is.
- **No game-level model**, so bets tied to a game total or result (a player
  over plus the game over) can't be priced.
- **Rebounds, assists and 3-pointers use only the rolling average**, not the
  learned model.
- **Untested live.** Everything above the "Evidence" line is design; only the
  scorecard can show it works.

## Answers to the questions people ask

**"Is this machine learning?"** Partly. One component (minutes) is a
gradient-boosted model. The rest is classical statistics on purpose: simple
parts that are easy to check beat a clever black box when the data is noisy
and the edge, if any, is small.

**"Why not just use a neural network or an LLM?"** The signal is thin and
the history is limited. A bigger model would mostly fit noise, and it would
be harder to tell whether it works. Anything fancier has to beat these
baselines on the scorecard first.

**"How do you know it isn't overfit or leaking the future?"** Predictions
use only earlier games, tests enforce that, and the learned model's settings
were chosen on one season and scored once on the next.

**"Does it beat the sportsbook?"** Unknown, and the system is built to find
out honestly: every pick is locked before the game, graded after, and
compared to the book's own probability. We don't claim an edge before the
record shows one.

**"What would you improve first?"** Injuries and lineups, then opponent
information. The perfect-minutes experiment shows that's where the headroom
is.

## Reproduce it

```powershell
.venv\Scripts\python scripts\nba_baseline_eval.py        # the rolling baselines, walk-forward
.venv\Scripts\python scripts\nba_minutes_eval.py         # minutes model vs baseline, with the oracle
.venv\Scripts\python scripts\nba_correlation_report.py   # same-game correlations
.venv\Scripts\python scripts\nba_props_settle.py         # the live scorecard
.venv\Scripts\python -m pytest                           # the leak-free tests among them
```
