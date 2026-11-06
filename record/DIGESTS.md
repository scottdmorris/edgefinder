# Published fingerprints of the pick log

Each line is the state of the tamper-evident pick log on a date: how many entries it held and
the fingerprint of the latest one. Committing a line here to the public repository gives it a
timestamp the operator does not control: GitHub records when it arrived. Anyone can later take
the log, recompute the fingerprints (`python scripts/verify_record.py`), and see that the
fingerprint they get at that many entries matches the one published here. A log that was
rewritten after the fact cannot match.

Add a line with `python scripts/verify_record.py --write-digest`, then commit and push it.

| Date | Entries | Fingerprint |
|---|---|---|
| 2026-11-05 | 813 | `c6fb4bab87e50559bc1fe52bc2977642498b7f7a4a8aef141bf6d39891aa5347` |
