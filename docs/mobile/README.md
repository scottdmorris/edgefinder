# Mobile audit

Screenshots of every tab at 375x812, 360x740 and 768x1024, before (`before/`) and after (`after/`)
the CSS fixes in `src/edgefinder/ui/theme.py`. `*-view.png` is the first screen; the other file is
a tall capture. Players shows a selected player. Measurements: `report.json` and
`players-report.json` in each folder.

Made with `scripts/make_demo_data.py` and `scripts/demo_app.py` (synthetic data, stubbed live feed;
player photos and logos show as broken images because the sandbox has no internet).

Targets under 44px, per screen: 47-101 before, 0-9 after. Page scroll width equals screen width in
every case, before and after. About was off-screen at 375 and 360 before, and reachable after.
