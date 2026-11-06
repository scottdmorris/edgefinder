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

**2. Four projections, same slot.**
- **`ewma-v1`, the baseline.** A weighted average of recent games, where
  recent ones count most and older ones fade. At the start of a season it
  leans on last season.
- **`minutes-v1`, the learned model.** Points = minutes × points per
  minute. A machine-learning model predicts the *minutes* from rest days,
  back-to-backs, workload and recent absences; we multiply by his recent
  scoring rate.
- **`context-v1`, the newest challenger.** The same inputs plus who else is
  out tonight (from the injury report), how weak the opposing defense is, and
  how fast the game should run. It is running alongside the others, not
  replacing them, until the record says it should.
- **`context-v2`, the sharpest.** Adds how often a player shoots and gets to
  the line, blends two views of the same game, and, importantly, sizes the
  uncertainty to each player (see below).

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

### Model 3: adding context (`context-v1`)
One gradient-boosted model predicts points directly from the same inputs as
model 2, plus three kinds of context:
- **Who's out.** A team's recent roster is everyone who played in its last ten
  games. Teammates on it who normally play 15+ minutes but aren't playing
  tonight are "lost": their typical minutes and points go missing, and
  someone has to cover them. Four numbers summarise that (minutes lost,
  points lost, starters lost, players out).
- **The opposing defense**, as points the opponent allows over its last ten
  games relative to the league.
- **Pace**, as possessions per game for both teams relative to the league.

Everything is worked out only from games before the one being projected. In
training, "out" is read from past box scores (who didn't play). Tonight it
comes from ESPN's free injury report, using the same roster and the same
definition, so the two match. If the report can't be fetched, the model
carries on as if nobody were out. The injury feed is unofficial, which is
fine for this but not something to build a paid product on.

**What it bought, honestly.** Scored once on 2025-26 after choosing on
2024-25, points error fell from 5.137 to 5.108, and the chances got better
calibrated (log score −3.317 → −3.304). That is a real improvement (the 95%
interval is entirely above zero) but a small one, about half a percent.
Opponent and pace added almost nothing beyond the absences, and a direct
points model *without* the context was slightly worse than model 2, so the gain
comes from the new information, not from the model type.

**One timing change came with it.** A projection made before the injury
report is published can't know who is out, so the pick-making snapshot is now
taken 2.5 to 4 hours before tip-off instead of at noon.

### Model 4: sharper chances (`context-v2`)
Three changes on top of model 3, each tested the same way (choose on 2024-25,
score 2025-26 once, see `scripts/nba_improve_eval.py`):
- **Shot habits as inputs.** Shots and free throws per minute (smoothed), how
  steady his scoring has been, and his points per minute this season.
  Attempts are steadier than points. On its own this was not distinguishable
  from zero.
- **A blend of two views.** The average of the direct points model and the
  minutes-times-rate model that also knows who is out. Together with the shot
  inputs, points error fell from 5.108 to 5.090 (about 0.4%; interval +0.006
  to +0.029). Real, but small.
- **Uncertainty that depends on the projection.** This was the big one. One
  fixed spread for everybody is wrong: a 6-point projection is far noisier,
  relative to its size, than a 25-point one (the fitted spread differs about
  6x). Letting it vary with the projection improved the log score from
  -3.302 to -3.234, about five times the gain from the changes to the
  projection itself, and it is out of sample. It matters where the bets are:
  "4+ points" on a role player, and big scorers' high lines.

What this does **not** show: that it beats FanDuel. These are measurements
against past games, not against posted lines. The live record is where that is
tested, and `context-v2` starts at zero graded picks like everything else.

### A record you do not have to take on trust
The ledger is a spreadsheet, and anyone with the file can edit it. So every row and every
result is also written to a second, append-only log (`data/nba_paper_log.chain.jsonl`).
Each entry carries a SHA-256 fingerprint of its own contents **and the previous entry's
fingerprint**, so changing, deleting or reordering anything in the past breaks every
fingerprint after it. The Record tab walks the log and compares it with the ledger: edited
rows, deleted rows, rows that were never logged, and results that differ from the one logged
are all named.

**What it proves, and what it doesn't.** On its own it proves little: whoever can edit the
ledger can also rebuild the whole log. What makes it trustworthy is publishing the *latest
fingerprint* somewhere the operator cannot rewrite. `python scripts/verify_record.py
--write-digest` adds a line (date, number of entries, fingerprint) to `record/DIGESTS.md`;
once that is committed to the public repository, the commit time is a timestamp the operator
does not control, and any later log must still contain that fingerprint at that entry number.
A log that was cut short or rewritten cannot reproduce it. To let a stranger check it, the
log and the ledger have to be shared, and until then only the operator can run the check.

**What it does not cover.** The 813 entries that existed when the log began (5 Nov 2026) were
imported, not witnessed, and are marked so; only entries after that were logged as they
happened. The time on an entry is the clock of the machine that wrote it. Closing prices
arrive after the fact and are not part of the log. The X+ ledger is not chained yet. A pick
is no longer written at all if its game has started.

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
- Adding who's out, the opponent and pace (`context-v1`) cut points error a
  further 0.6% (5.137 → 5.108, interval +0.005 to +0.051 points). Together the
  two models close about 12% of the gap between the plain average and
  perfect minutes. That is progress, but most of the gap remains.
- Historical absences are read from box scores, which includes late scratches
  and coaches' decisions that an injury report published hours before tip-off
  can't show. So the live gain may be smaller than the offline one.

**Live (paper tracking):** the tracker started on 2026-11-04 and nothing has
settled yet. There is no live track record to report, and we say so. The
first results land on 2026-11-05.

## What it does not do
- **Injuries are only partly covered.** `context-v1` uses the injury report, but
  the other two models don't, the report is an unofficial feed, and a
  late scratch after the snapshot is invisible. Nothing yet adjusts for *how
  much* a specific star's absence matters beyond his typical minutes.
- **Opponent information is thin.** `context-v1` knows the opponent's recent
  defense and pace, nothing about matchups (a big against a small lineup),
  and `ewma-v1` and `minutes-v1` know nothing about the opponent at all.
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

**"What would you improve first?"** Injuries and lineups were first, and the
first version is built: it helped by about half a percent, which is real but
modest. The perfect-minutes experiment says there's much more headroom, so the
next steps are modelling how much each specific player's absence matters,
taking the snapshot as late as the budget allows, and, once there's a live
record, letting results tune how much weight the models get.

**"Can I ask it questions in plain English?"** For one kind of question,
yes: how often a player went over, under or reached a number in points,
rebounds, assists or 3-pointers ("Brunson over 24 in his last 10"). It is
counting, not modelling: a rule-based reader turns the question into a
structured query and code tallies the games in the log, with no language
model involved. If the question is ambiguous (two Johnsons) or outside that
scope, it says so instead of guessing.

## Reproduce it

```powershell
.venv\Scripts\python scripts\nba_baseline_eval.py        # the rolling baselines, walk-forward
.venv\Scripts\python scripts\nba_minutes_eval.py         # minutes model vs baseline, with the oracle
.venv\Scripts\python scripts\nba_context_eval.py         # who's out + opponent + pace, scored once
.venv\Scripts\python scripts\nba_correlation_report.py   # same-game correlations
.venv\Scripts\python scripts\nba_props_settle.py         # the live scorecard
.venv\Scripts\python -m pytest                           # the leak-free tests among them
```
