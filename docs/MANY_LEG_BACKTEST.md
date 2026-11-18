# Do slips with many legs pay?

The Parlay screen's **Long shot** style builds one slip of 8 to 10 legs a night. Before it was
added, the idea was tested on last season's markets. `scripts/nba_many_leg_backtest.py`
reproduces these tables from the rows the season backtest saved
([KALSHI_BACKTEST.md](KALSHI_BACKTEST.md)).

**The test.** Each night of 2025-26, one slip from Kalshi player-points markets. The legs are
the likeliest markets by the app's 30/70 blend of the Smarter model and Kalshi's price. Each
player gets at most one leg, and each game gets one or two legs. Legs come from the night's eight
busiest games, the same limit the snapshot budget sets. Each slip is priced two ways:
- **At Kalshi prices:** the product of the asks, plus Kalshi's fee on each leg. These are
  prices you could actually pay.
- **Sportsbook-style:** the midpoint with a 4.5% cut per leg, the margin a -110/-110 book takes.

## All markets

| Legs | A game | Nights | Won | Typical payout | Return at Kalshi prices | 95% interval | Return, sportsbook-style |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 1 | 136 | 80% | +12 | -5% | -14% to +3% | -3% |
| 3 | 1 | 130 | 68% | +29 | -9% | -21% to +3% | -4% |
| 4 | 1 | 119 | 57% | +46 | -15% | -30% to +1% | -12% |
| 6 | 1 | 96 | 40% | +113 | -25% | -45% to -3% | -19% |
| 8 | 1 | 53 | 40% | +251 | +30% | -17% to +78% | +47% |
| 8 | 2 | 113 | 31% | +185 | -5% | -39% to +36% | +69% |
| 10 | 2 | 103 | 18% | +352 | -32% | -64% to +3% | -17% |

## Only markets with a tight spread (ask within 4 cents of the bid)

| Legs | A game | Nights | Won | Typical payout | Return at Kalshi prices | 95% interval | Return, sportsbook-style |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 1 | 122 | 66% | +36 | -5% | -19% to +8% | -8% |
| 3 | 1 | 113 | 51% | +72 | -9% | -28% to +11% | -13% |
| 4 | 1 | 103 | 35% | +123 | -9% | -40% to +30% | -12% |
| 6 | 1 | 77 | 16% | +353 | -37% | -83% to +26% | -37% |
| 8 | 1 | 39 | 5% | +1002 | -81% | -117% to -29% | -74% |
| 8 | 2 | 94 | 9% | +686 | -8% | -101% to +163% | -10% |
| 10 | 2 | 76 | 5% | +1595 | -72% | -117% to -15% | -65% |

Kalshi's fee is charged on each leg, so a losing slip can cost more than its stake (below -100%).

## What it says

- **Every extra leg adds the cut again.** Two or three legs sit near break-even. Four to six
  legs lose 15% to 37%.
- **The 10-leg, two-a-game rule that the Long shot style uses lost 32% at Kalshi prices.** It won
  18% of nights at a typical +352, and the interval runs from -64% to +3%.
- **The rows that look profitable are thin markets.** The 8-leg rows gain only when wide-spread
  markets are included, and there the midpoint overstates what a slip pays. With tight spreads
  they lose too, on 39 to 113 nights with wide intervals.
- **The app's rule adds one filter the test leaves out:** each leg must be worth betting on its
  own (2%+ expected value) and pass the quote checks.

So the Long shot style is offered for fun and tracked on paper: one slip a night goes into the
`long-shot-v1` trial on the Record tab. It is not offered as an edge.
