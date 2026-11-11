# Kalshi backtest, 2025-26

Generated Nov 11, 2026 by `scripts/nba_kalshi_backtest.py`.

**13,443 settled player-points markets** on 136 game nights and 136 players, each priced by Kalshi before tip-off and by every model.

## What was kept

| Step | Markets |
|---|---:|
| archived | 23,562 |
| clean result | 22,557 |
| tip-off confirmed | 22,373 |
| quoted before tip | 18,209 |
| matched to a projection | 13,443 |
| result agrees with box score | 13,443 |

Only rotation players (20+ minutes a game before the game) have projections, and a market needs a two-sided quote in the hour before tip-off.

## 1. Who is more accurate?

"Corrected" applies the role correction curves (bench, rotation, starter) fitted on 2024-25 only, so this season is new to them too.

Brier score: the average squared gap between the chance given and what happened (lower is better). A negative "vs Kalshi" means more accurate than Kalshi's own price. The interval resamples whole game nights.

| Prices from | Brier | vs Kalshi | 95% interval |
|---|---|---|---|
| Kalshi (mid price) | 0.1846 |  |  |
| Simple | 0.1908 | +0.0062 | +0.0037 to +0.0087 |
| Simple, corrected | 0.1905 | +0.0059 | +0.0036 to +0.0084 |
| Simple 30/70 with Kalshi | 0.1841 | -0.0005 | -0.0014 to +0.0003 |
| Simple, corrected, 30/70 with Kalshi | 0.1841 | -0.0006 | -0.0014 to +0.0002 |
| Smarter | 0.1877 | +0.0031 | +0.0009 to +0.0051 |
| Smarter, corrected | 0.1873 | +0.0027 | +0.0005 to +0.0047 |
| Smarter 30/70 with Kalshi | 0.1838 | -0.0008 | -0.0015 to -0.0001 |
| Smarter, corrected, 30/70 with Kalshi | 0.1837 | -0.0009 | -0.0017 to -0.0002 |
| Smartest * | 0.1875 | +0.0029 | +0.0006 to +0.0051 |
| Smartest, corrected * | 0.1871 | +0.0025 | -0.0001 to +0.0049 |
| Smartest 30/70 with Kalshi * | 0.1838 | -0.0008 | -0.0017 to -0.0001 |
| Smartest, corrected, 30/70 with Kalshi * | 0.1836 | -0.0010 | -0.0018 to -0.0002 |
| Sharpest * | 0.1861 | +0.0014 | -0.0008 to +0.0035 |
| Sharpest, corrected * | 0.1860 | +0.0014 | -0.0009 to +0.0035 |
| Sharpest 30/70 with Kalshi * | 0.1835 | -0.0011 | -0.0019 to -0.0004 |
| Sharpest, corrected, 30/70 with Kalshi * | 0.1835 | -0.0011 | -0.0019 to -0.0004 |

\* Uses who sat out, read from who actually played. That includes late scratches the market could not have priced, so it flatters these models here.

## 2. Would the recording rules have made money?

Every bet the rule picks, 1 unit each, bought at Kalshi's ask (or 1 minus the bid for No) and paying Kalshi's taker fee. "Return" is profit per unit staked.

| Model | Rule | Bets | Won | Typical price | Units | Return | 95% interval |
|---|---|---|---|---|---|---|---|
| Simple | 2%+ value only | 1933 | 32.5% | 0.32 | -231.2 | -12.0% | -21.8% to -1.9% |
| Simple | with guardrails | 358 | 45.0% | 0.41 | -13.3 | -3.7% | -16.0% to +10.1% |
| Smarter | 2%+ value only | 1163 | 31.2% | 0.29 | -69.2 | -5.9% | -19.1% to +7.9% |
| Smarter | with guardrails | 269 | 44.6% | 0.38 | +4.4 | +1.6% | -11.8% to +16.2% |
| Smartest * | 2%+ value only | 1166 | 29.8% | 0.29 | -122.4 | -10.5% | -24.3% to +2.6% |
| Smartest * | with guardrails | 281 | 37.7% | 0.39 | -46.8 | -16.7% | -30.3% to -2.7% |
| Sharpest * | 2%+ value only | 756 | 35.6% | 0.36 | -9.2 | -1.2% | -19.7% to +18.3% |
| Sharpest * | with guardrails | 238 | 40.3% | 0.41 | -28.3 | -11.9% | -26.6% to +4.9% |
| Simple corrected | 2%+ value only | 1839 | 33.3% | 0.32 | -116.6 | -6.3% | -16.7% to +4.3% |
| Simple corrected | with guardrails | 364 | 45.3% | 0.40 | +7.8 | +2.1% | -15.1% to +18.5% |
| Smarter corrected | 2%+ value only | 1051 | 29.2% | 0.26 | -18.5 | -1.8% | -19.4% to +14.7% |
| Smarter corrected | with guardrails | 250 | 41.6% | 0.37 | -2.2 | -0.9% | -19.5% to +18.1% |
| Smartest corrected * | 2%+ value only | 1089 | 28.1% | 0.25 | -65.3 | -6.0% | -22.0% to +10.0% |
| Smartest corrected * | with guardrails | 259 | 34.4% | 0.40 | -63.5 | -24.5% | -38.9% to -9.7% |
| Sharpest corrected * | 2%+ value only | 709 | 32.2% | 0.30 | +0.7 | +0.1% | -20.1% to +19.9% |
| Sharpest corrected * | with guardrails | 189 | 42.9% | 0.41 | -4.1 | -2.2% | -19.5% to +16.2% |

### Simple model, by the price paid (2%+ value only)

| price | bets | won | units | roi |
|---|---|---|---|---|
| (0.0, 0.2] | 586 | 9.7 | -149.5 | -25.5 |
| (0.2, 0.35] | 499 | 28.3 | -21.9 | -4.4 |
| (0.35, 0.5] | 435 | 39.8 | -49.8 | -11.4 |
| (0.5, 0.65] | 291 | 56.7 | -11.2 | -3.8 |
| (0.65, 0.8] | 104 | 74.0 | 1.3 | 1.2 |
| (0.8, 1.0] | 18 | 83.3 | -0.1 | -0.7 |

### The same, with the role correction

| price | bets | won | units | roi |
|---|---|---|---|---|
| (0.0, 0.2] | 526 | 11.8 | -43.3 | -8.2 |
| (0.2, 0.35] | 500 | 29.6 | 2.4 | 0.5 |
| (0.35, 0.5] | 421 | 38.2 | -64.8 | -15.4 |
| (0.5, 0.65] | 278 | 55.8 | -15.0 | -5.4 |
| (0.65, 0.8] | 100 | 75.0 | 3.8 | 3.8 |
| (0.8, 1.0] | 14 | 85.7 | 0.2 | 1.5 |

## 3. Is Kalshi's price honest?

Markets grouped by Kalshi's mid price before tip-off (all numbers in %).

| mid | markets | kalshi_said | happened | simple_said | simple_corrected | smarter_said | smarter_corrected |
|---|---|---|---|---|---|---|---|
| (-0.001, 0.1] | 1609 | 6.9 | 8.1 | 10.4 | 10.2 | 10.2 | 10.2 |
| (0.1, 0.2] | 1910 | 14.9 | 16.2 | 18.4 | 18.0 | 18.2 | 18.8 |
| (0.2, 0.3] | 1677 | 25.2 | 25.6 | 27.5 | 27.8 | 27.4 | 29.0 |
| (0.3, 0.4] | 1314 | 35.1 | 40.0 | 36.6 | 37.2 | 36.5 | 38.7 |
| (0.4, 0.5] | 1733 | 45.7 | 46.5 | 44.7 | 45.5 | 44.6 | 47.1 |
| (0.5, 0.6] | 1558 | 54.9 | 54.4 | 50.7 | 51.6 | 51.1 | 54.1 |
| (0.6, 0.7] | 1356 | 65.3 | 66.0 | 60.9 | 62.0 | 61.2 | 64.3 |
| (0.7, 0.8] | 1302 | 75.0 | 75.8 | 70.0 | 70.9 | 70.3 | 72.7 |
| (0.8, 0.9] | 770 | 84.3 | 84.9 | 79.3 | 79.5 | 79.8 | 81.0 |
| (0.9, 1.0] | 214 | 92.4 | 93.0 | 88.3 | 87.5 | 88.9 | 88.5 |

## 4. Did the models' edge last?

The season cut at its middle game night. Each model column is the 30/70 blend's Brier score minus Kalshi's (negative is better than Kalshi), with its interval.

| Nights | Markets | Kalshi Brier | Simple | Smarter | Smartest * | Sharpest * |
|---|---|---|---|---|---|---|
| Before 2026-01-28 | 4582 | 0.1972 | -0.0018 (-0.0035 to -0.0002) | -0.0021 (-0.0038 to -0.0005) | -0.0025 (-0.0044 to -0.0009) | -0.0026 (-0.0044 to -0.0010) |
| From 2026-01-28 | 8861 | 0.1781 | +0.0002 (-0.0007 to +0.0010) | -0.0001 (-0.0008 to +0.0005) | +0.0000 (-0.0006 to +0.0007) | -0.0003 (-0.0009 to +0.0003) |

Player-points markets were new on Kalshi early in the season. If the blend only beats Kalshi in the early half, the models were ahead of a young market, not of the market as it prices now.

## 5. Are consistent players easy locks?

Every market, grouped by how often the player reached that number in his last 20 games before this one, and what buying Yes at the ask returned.

| Reached it in his last 20 | Markets | Kalshi's ask | Happened | Return buying Yes | 95% interval |
|---|---|---|---|---|---|
| up to 20% | 3980 | 17.6% | 15.5% | -15.2% | -25.6% to -4.8% |
| 20% to 40% | 2828 | 37.2% | 33.4% | -14.0% | -19.7% to -8.4% |
| 40% to 60% | 2798 | 54.3% | 51.7% | -7.9% | -12.1% to -3.8% |
| 60% to 80% | 2477 | 70.3% | 67.0% | -6.9% | -10.1% to -4.0% |
| 80% to 90% | 949 | 82.1% | 80.1% | -3.8% | -7.3% to -0.5% |
| 90% to 100% | 411 | 88.2% | 87.1% | -2.2% | -5.9% to +1.6% |

**A nightly 3-leg slip of the steadiest favourites** (reached the number in 90%+ of the last 20 games, priced 80%+, one leg a player): 81 nights, average cost 0.77, won 74.1%, return -6.2% (95% interval -18.5% to +5.9%). The legs are priced as independent, which is how Kalshi would sell them one by one.

## Limits

- One season. The models never saw it, but the rules and spreads were chosen with earlier seasons, and this test was run once after the fact.
- Prices are the last hourly quote at least 15 minutes before tip-off; a real bet an hour or more earlier would have got a different price, and a big order would move it.
- Fees are Kalshi's taker formula (7% x price x (1 - price) per contract) without rounding up to the cent, which costs a little more on small orders.
- Bets on one player's ladder, and players in one game, are not independent; the intervals account for that by resampling whole nights, but they are still approximate.
