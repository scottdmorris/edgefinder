# Higher-hit trial v1

This is a prospective paper experiment, not a claim that the model wins 60% of bets.
No past nights are backfilled. The first qualifying slip per Eastern game day is retained;
later suggestions cannot replace it because their outcome looks better.

## Frozen rules

- FanDuel, context-v2, Higher hit rate, exactly two different players in different games.
- At least 60% estimated joint probability, at least 1.30 decimal simulated total return,
  and at least 2% estimated EV per unit. Existing per-leg guardrails still apply.
- Each player has at least 10 games before the projected day. Minutes coefficient of
  variation over the last 10 games is at most .25; the last three minutes average is
  within 25% of the last ten; the player played within the last seven days, with no team change in the last ten games.
- Each recorded price is at most 90 minutes old, recorded before tip, with no changed
  main-line number. No verified injury-report requirement: that evidence is not captured.
- No slip is a valid outcome of the selection rules. Never loosen rules to fill a day.
- Trigger: each early snapshot cycle, and Higher hit rate suggestions offered in the app.
- The SQLite archive freezes the protocol and hashes of the selection, calibration,
  quality and integration code. Rule changes require a new experiment ID. Original
  offered payloads cannot be updated; settlement is stored separately.

## Scoring

Review after at least 200 graded trial slips AND at least 30 graded game days. Report
hit rate, flat-one-unit return, pending/void counts, and Brier score against the quoted
market baseline (1 / simulated product payout, margin included). Exclude slips with
voided legs from probability calibration; reduce their simulated payout appropriately.
Success requires positive return and a lower Brier score than that baseline; it is still
provisional without a date-blocked uncertainty interval and an independent continuation.
A point estimate above zero is not proof of a persistent edge.

The payout is a product of quoted single-leg prices, not an executable sportsbook parlay
quote. This is especially important for same-game slips outside the trial. All results
are before fees, exclusions, limits and execution changes. The broader offered-slip
record counts distinct API suggestions, not people, display impressions, clicks or money.

The data file is data/suggested_slips.sqlite3 (git-ignored). The morning settle grades
pending offers, and the Record screen displays the offered record and the trial separately.
