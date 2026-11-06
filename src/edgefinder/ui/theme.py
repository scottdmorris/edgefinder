"""The look: pure black, hairline dividers, white pill buttons, and as little
chrome as possible, so the players, prices and numbers are what you see.

One palette lives here. Everything below is written in terms of it, so the
look can change in one place.
"""

BLUE = "#EFF3F4"
GREEN = "#00BA7C"
AMBER = "#F5B83D"
RED = "#F4212E"

BG = "#000000"
RAISED = "#16181C"        # the one step lighter than the page: hero boxes, hover
LINE = "#2F3336"          # every divider and border
LINE_STRONG = "#536471"   # outlined buttons
TEXT = "#E7E9EA"
MUTED = "#71767B"
BUTTON = "#EFF3F4"        # the white pill
BUTTON_TEXT = "#0F1419"

CSS = f"""
<style>
.stApp {{ background: {BG}; }}
.block-container {{ padding-top: 1.1rem; padding-bottom: 5rem; max-width: 1180px; }}
header[data-testid="stHeader"] {{ display: none; }}
h1, h2, h3, h4 {{ letter-spacing: -0.02em; font-weight: 800; }}
h2 {{ font-size: 1.6rem !important; }}
h4 {{ font-size: 1.1rem !important; margin-top: .8rem; }}
hr {{ border-color: {LINE} !important; }}

/* the app is its own thing: no sidebar, no deploy bar */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] {{ display: none !important; }}

/* long documents inside the app: smaller headings than a web page would use */
.st-key-about h1 {{ font-size: 1.7rem !important; }}
.st-key-about h2 {{ font-size: 1.3rem !important; margin-top: 1.4rem; }}
.st-key-about h3 {{ font-size: 1.05rem !important; }}
.st-key-about table {{ font-size: 0.88rem; }}

/* tabs: quiet text, the current one white, a blue bar under it */
/* navigation: a pill bar, the open view filled white (Streamlit 1.59: role=tablist + stTab) */
.stTabs [role="tablist"] {{ gap: 4px; border-bottom: 0; background: {RAISED};
  padding: 5px; border-radius: 999px; width: fit-content; max-width: 100%; overflow-x: auto;
  border: 1px solid {LINE}; margin-bottom: 18px; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"],
.stTabs .react-aria-SelectionIndicator {{ display: none; }}
.stTabs [data-testid="stTab"] {{ font-weight: 600; padding: 9px 16px; color: {MUTED};
  border-radius: 999px; transition: background .15s ease, color .15s ease; }}
.stTabs [data-testid="stTab"]:hover {{ color: {TEXT}; }}
.stTabs [data-testid="stTab"][aria-selected="true"] {{ color: {BUTTON_TEXT} !important;
  background: {BUTTON}; font-weight: 800; }}
.stTabs [data-testid="stTab"][aria-selected="true"] * {{ color: {BUTTON_TEXT} !important; }}

/* the top bar */
.bk-appbar {{ display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 4px 2px 16px; }}
.bk-appbar-brand {{ display: flex; align-items: center; gap: 10px; }}
.bk-appbar-logo {{ width: 34px; height: 34px; }}
.bk-appbar-name {{ font-weight: 900; font-size: 1.3rem; letter-spacing: -.01em; }}
.bk-appbar-chips {{ display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }}
.bk-chip {{ font-size: .78rem; font-weight: 700; padding: 6px 12px; border-radius: 999px;
  background: {RAISED}; border: 1px solid {LINE}; color: {MUTED}; white-space: nowrap; }}
.bk-chip.live {{ color: {GREEN}; border-color: rgba(0,186,124,.45); }}
.bk-chip.live::before {{ content: ""; display: inline-block; width: 7px; height: 7px;
  margin-right: 6px; border-radius: 999px; background: {GREEN}; vertical-align: 1px;
  animation: bk-pulse 1.6s ease-in-out infinite; }}
.bk-chip.warn {{ color: {AMBER}; border-color: rgba(245,184,61,.45); }}

/* a row of big numbers */
.bk-strip {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 2px 0 16px; }}
.bk-strip-cell {{ flex: 1 1 110px; padding: 12px 14px; border-radius: 16px;
  background: {RAISED}; border: 1px solid {LINE}; }}
.bk-strip-cell b {{ display: block; font-size: 1.5rem; font-weight: 900; line-height: 1.1; }}
.bk-strip-cell span {{ font-size: .74rem; color: {MUTED}; font-weight: 600;
  text-transform: uppercase; letter-spacing: .05em; }}
[data-testid="stTab"] {{ font-weight: 500; color: {MUTED}; }}
[data-testid="stTab"][aria-selected="true"] {{ color: {TEXT}; font-weight: 800; }}

/* heads-up boxes keep the black look: no default blue/yellow/green fills */
[data-testid="stAlert"] {{ background: {RAISED} !important; border: 1px solid {LINE};
  border-radius: 16px; color: {TEXT}; }}
[data-testid="stAlertContainer"] {{ background: transparent !important; color: {TEXT} !important; }}
[data-testid^="stAlertContent"] {{ color: {TEXT} !important; }}

/* buttons are pills: outlined, with the chosen one filled white */
.stButton > button, .stDownloadButton > button {{
  border-radius: 999px; border: 1px solid {LINE_STRONG}; background: transparent;
  color: {TEXT}; font-weight: 700;
}}
.stButton > button:hover {{ background: rgba(239,243,244,0.1); border-color: {LINE_STRONG};
  color: {TEXT}; }}
.stButton > button[kind="primary"] {{ background: {BUTTON}; border-color: {BUTTON};
  color: {BUTTON_TEXT}; }}
.stButton > button[kind="primary"]:hover {{ background: #D7DBDC; border-color: #D7DBDC;
  color: {BUTTON_TEXT}; }}
[data-testid="stBaseButton-pills"], [data-testid="stBaseButton-pillsActive"] {{
  border-radius: 999px; border: 1px solid {LINE}; background: transparent; color: {MUTED};
  font-weight: 500;
}}
[data-testid="stBaseButton-pillsActive"] {{ background: {BUTTON}; border-color: {BUTTON};
  color: {BUTTON_TEXT}; font-weight: 800; }}

/* fields and boxes lose the default look */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div {{
  background: {BG} !important; border-color: {LINE} !important; border-radius: 12px !important;
}}
[data-testid="stExpander"] {{ border: 1px solid {LINE}; border-radius: 16px; background: transparent; }}
[data-testid="stExpander"] summary:hover {{ background: {RAISED}; }}
[data-testid="stMetric"] {{
  background: transparent; border: 1px solid {LINE}; border-radius: 16px; padding: 14px 16px;
}}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 0.8rem; }}

/* the slip summary stays in view while you scroll past the list */
[data-testid="stLayoutWrapper"]:has(> .st-key-slip-bar) {{
  position: sticky; top: 3.5rem; z-index: 60; background: {BG};
}}
.st-key-slip-bar {{ padding: 8px 0 6px; border-bottom: 1px solid {LINE}; }}
/* rows of buttons stay on one line, even on a phone */
[class*="st-key-browse-list"] [data-testid="stHorizontalBlock"],
.st-key-slip-panel [data-testid="stHorizontalBlock"],
.st-key-slip-bar [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: .5rem; }}
[class*="st-key-browse-list"] [data-testid="stColumn"],
.st-key-slip-panel [data-testid="stColumn"],
.st-key-slip-bar [data-testid="stColumn"] {{ min-width: 0 !important; }}
.bk-note {{
  padding: 10px 14px; border-radius: 12px; font-size: 0.85rem; color: {MUTED};
  background: {RAISED}; border: 1px solid {LINE}; margin: 8px 0;
}}
.bk-footer {{
  margin-top: 2.5rem; padding-top: 14px; border-top: 1px solid {LINE};
  color: {MUTED}; font-size: 0.78rem; line-height: 1.5;
}}

.bk-card {{
  display: flex; align-items: center; gap: 14px; padding: 12px 14px; margin: 8px 0;
  background: transparent; border: 1px solid {LINE}; border-left: 3px solid transparent;
  border-radius: 16px;
}}
.bk-card.hit {{ border-left-color: {GREEN}; }}
.bk-card.alive {{ border-left-color: {AMBER}; }}
.bk-card.missed {{ border-left-color: {RED}; }}
.bk-card.compact {{ gap: 10px; padding: 8px 10px; margin: 5px 0; }}
.bk-card.compact .bk-photo {{ width: 56px; height: 46px; }}
.bk-card.compact .bk-title {{ font-size: 0.92rem; }}
.bk-card.compact .bk-sub {{ font-size: 0.76rem; }}
.bk-card.compact .bk-pill {{ min-width: 50px; padding: 6px 8px; font-size: 0.85rem; }}
/* players are shown as cutouts standing on the card: no circle, no crop, no backdrop */
.bk-photo {{
  width: 68px; height: 56px; object-fit: contain; object-position: center bottom; flex: none;
}}
.bk-body {{ flex: 1; min-width: 0; }}
.bk-title {{ font-weight: 800; font-size: 1rem; line-height: 1.25; display: flex;
  align-items: center; }}
.bk-sub {{ color: {MUTED}; font-size: 0.82rem; margin-top: 2px; }}
.bk-bar {{ height: 6px; border-radius: 6px; background: {RAISED}; margin-top: 8px; overflow: hidden; }}
.bk-bar > div {{ height: 100%; border-radius: 6px; background: {BLUE}; }}
.bk-card.hit .bk-bar > div {{ background: {GREEN}; }}
.bk-card.alive .bk-bar > div {{ background: {AMBER}; }}
.bk-card.missed .bk-bar > div {{ background: {RED}; }}
.bk-pill {{
  flex: none; min-width: 64px; text-align: center; padding: 7px 12px; border-radius: 999px;
  font-weight: 800; font-size: 0.92rem; border: 1px solid {LINE}; color: {BLUE};
  background: transparent;
}}
.bk-pill.hit {{ border-color: {GREEN}; color: {GREEN}; }}
.bk-pill.alive {{ border-color: {AMBER}; color: {AMBER}; }}
.bk-pill.missed {{ border-color: {RED}; color: {RED}; }}
.bk-pill.neutral {{ color: {MUTED}; }}

.bk-idea {{ border: 1px solid {LINE}; border-radius: 16px; padding: 4px 14px 12px; margin: 10px 0 4px; }}
.bk-idea .bk-leg {{ display: flex; align-items: center; gap: 10px; padding: 9px 0;
  border-bottom: 1px solid {LINE}; }}
.bk-idea .bk-leg:last-of-type {{ border-bottom: 0; }}
.bk-idea .bk-leg .bk-body {{ min-width: 0; }}
.bk-idea-foot {{ color: {MUTED}; font-size: 0.82rem; padding-top: 6px; }}
.bk-idea-foot b {{ color: {TEXT}; }}

.bk-slip {{
  margin: 14px 0; padding: 16px 18px; border-radius: 16px;
  background: {RAISED}; border: 1px solid {LINE};
}}
.bk-slip-head {{ color: {MUTED}; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.06em; }}
.bk-slip-big {{ font-size: 2rem; font-weight: 800; line-height: 1.15; margin-top: 4px; }}
.bk-slip-row {{ display: flex; gap: 28px; flex-wrap: wrap; margin-top: 10px; }}
.bk-slip-row > div > span {{ display: block; }}
.bk-slip-k {{ color: {MUTED}; font-size: 0.75rem; }}
.bk-slip-v {{ font-weight: 700; font-size: 1.05rem; }}
.bk-game {{
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; margin: 6px 0; background: transparent; border: 1px solid {LINE};
  border-radius: 16px;
}}
.bk-game.live {{ border-color: {GREEN}; }}
.bk-team {{ border-left: 3px solid transparent; padding-left: 8px; }}
.bk-tiny-logo {{ width: 18px; height: 18px; object-fit: contain; margin-right: 7px;
  vertical-align: -3px; }}
.bk-banner {{
  display: flex; align-items: flex-end; gap: 18px; padding: 16px 18px 0; border-radius: 18px;
  border: 1px solid {LINE}; margin-bottom: 12px; overflow: hidden;
}}
.bk-banner-photo {{ height: 138px; width: auto; flex: none; display: block; }}
.bk-banner-text {{ padding-bottom: 18px; }}
.bk-banner-name {{ font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.1; }}
.bk-banner-sub {{ color: {TEXT}; margin-top: 6px; display: flex; align-items: center;
  font-size: 0.95rem; }}
.bk-tile {{
  background: transparent; border: 1px solid {LINE}; border-top: 1px solid {LINE};
  border-radius: 16px; padding: 12px 8px; text-align: center;
}}
.bk-tile-value {{ font-size: 1.7rem; font-weight: 800; line-height: 1.1; }}
.bk-tile-label {{ color: {MUTED}; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; margin-top: 4px; }}
.bk-teams {{ flex: 1; }}
.bk-team {{ display: flex; align-items: center; gap: 10px; padding: 3px 0; color: {MUTED}; }}
.bk-team.lead {{ color: {TEXT}; font-weight: 800; }}
.bk-team {{ position: relative; }}
.bk-team b {{ margin-left: auto; font-size: 1.05rem; }}
/* a basket: the score flashes and "+3" floats up beside it */
.bk-pop {{ position: absolute; right: 2.6rem; top: -0.2rem; font-weight: 800; font-size: 0.95rem;
  color: {GREEN}; pointer-events: none; animation: bk-rise 2.4s ease-out forwards; }}
.bk-pop.p3 {{ font-size: 1.25rem; }}
.bk-team.scored b {{ animation: bk-flash 1.8s ease-out; }}
@keyframes bk-rise {{
  0% {{ opacity: 0; transform: translateY(8px) scale(0.8); }}
  15% {{ opacity: 1; transform: translateY(0) scale(1.2); }}
  100% {{ opacity: 0; transform: translateY(-22px) scale(1); }}
}}
@keyframes bk-flash {{
  0% {{ color: {GREEN}; transform: scale(1.35); }}
  100% {{ color: inherit; transform: scale(1); }}
}}
@media (prefers-reduced-motion: reduce) {{
  .bk-pop, .bk-team.scored b, .bk-feed.new, .bk-card.flash, .bk-shot.fresh, .bk-chip.live::before, .bk-hero-team.scored .bk-hero-score,
  .bk-hero.live .bk-hero-badge::before {{ animation: none; }}
  .bk-card, .bk-idea, .bk-game {{ transition: none; }}
}}
.bk-logo {{ width: 26px; height: 26px; object-fit: contain; flex: none; }}
.bk-game-status {{ font-size: 0.78rem; font-weight: 700; color: {MUTED}; text-align: right; flex: none; }}
.bk-game.live .bk-game-status {{ color: {GREEN}; }}
/* on a wide screen the whole right-hand column (the slip) stays in view */
[data-testid="stColumn"]:has(.st-key-slip-panel) {{
  position: sticky; top: 7.2rem; align-self: flex-start;
  max-height: calc(100vh - 8rem); overflow-y: auto; padding-right: 4px;
  /* Streamlit pulls markdown blocks up by 1rem, so without this the bottom of the
     last card pokes out of the column and gets clipped */
  padding-bottom: 1.2rem;
}}
.bk-cmp {{ padding: 7px 0; }}
.bk-cmp-top {{ display: flex; justify-content: space-between; align-items: baseline; gap: 8px;
  font-size: 0.92rem; }}
.bk-cmp-label {{ color: {MUTED}; font-size: 0.78rem; text-align: center; flex: 1; }}
.bk-cmp-val {{ min-width: 92px; font-weight: 600; color: {MUTED}; }}
.bk-cmp-val:last-child {{ text-align: right; }}
.bk-cmp-val.lead {{ color: {TEXT}; font-weight: 800; }}
.bk-cmp-bar {{ display: flex; height: 6px; border-radius: 5px; overflow: hidden; margin-top: 4px;
  background: {RAISED}; gap: 2px; }}
.bk-cmp-bar .away {{ background: {BLUE}; }}
.bk-cmp-bar .home {{ background: {AMBER}; }}
.bk-leader {{ display: flex; align-items: center; gap: 12px; padding: 8px 10px; margin: 6px 0;
  background: transparent; border: 1px solid {LINE}; border-radius: 16px; }}
.bk-photo.small {{ width: 54px; height: 44px; }}
.bk-leader-stat {{ text-align: right; flex: none; }}
.bk-leader-stat b {{ font-size: 1.3rem; display: block; line-height: 1.1; }}
.bk-leader-stat span {{ color: {MUTED}; font-size: 0.72rem; }}
.bk-empty {{
  text-align: center; padding: 28px 16px; border: 1.5px dashed {LINE_STRONG}; border-radius: 16px;
}}
.bk-empty-title {{ font-weight: 800; margin-bottom: 4px; }}
.bk-feed {{ padding: 8px 0 8px 10px; border-bottom: 1px solid {LINE};
  border-left: 3px solid transparent; }}
.bk-feed.new {{ animation: bk-slide-in .5s ease-out, bk-glow 2.5s ease-out; }}
.bk-feed:last-child {{ border-bottom: 0; }}
.bk-feed-time {{ color: {MUTED}; font-size: 0.78rem; font-weight: 700; }}
.bk-feed-score {{ color: {MUTED}; font-size: 0.78rem; float: right; }}

.bk-chance {{ font-size: 1.5rem; font-weight: 800; line-height: 1.1; text-align: right; }}
.bk-chance span {{ display: block; font-size: 0.72rem; font-weight: 600; color: {MUTED}; }}

/* the open game, big, in both teams' colors */
.bk-hero {{ display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 12px;
  padding: 18px 20px; margin: 6px 0 14px; border: 1px solid {LINE}; border-radius: 20px; }}
.bk-hero.live {{ border-color: {GREEN}; }}
.bk-hero-team {{ position: relative; display: grid; justify-items: center; gap: 2px; color: {MUTED}; }}
.bk-hero-team.lead {{ color: {TEXT}; }}
.bk-hero-logo {{ width: 56px; height: 56px; object-fit: contain; }}
.bk-hero-code {{ font-weight: 800; font-size: 1rem; letter-spacing: .04em; }}
.bk-hero-score {{ position: relative; font-size: 3rem; font-weight: 900; line-height: 1; }}
.bk-hero-team.scored .bk-hero-score {{ animation: bk-flash 1.8s ease-out; }}
.bk-hero-score .bk-pop {{ right: -2.2rem; top: 0; }}
.bk-hero-note {{ font-size: .75rem; color: {MUTED}; text-align: center; min-height: 1em; }}
.bk-hero-mid {{ display: grid; justify-items: center; gap: 4px; }}
.bk-hero-badge {{ font-size: .7rem; font-weight: 800; letter-spacing: .12em; color: {MUTED}; }}
.bk-hero.live .bk-hero-badge {{ color: {GREEN}; }}
.bk-hero-clock {{ font-size: .95rem; font-weight: 700; white-space: nowrap; }}

/* motion: only ever on a change, never on a plain refresh */
.bk-hero.live .bk-hero-badge::before {{ content: ""; display: inline-block; width: 7px; height: 7px;
  margin-right: 6px; border-radius: 999px; background: {GREEN}; vertical-align: 1px;
  animation: bk-pulse 1.6s ease-in-out infinite; }}
.bk-card.flash {{ animation: bk-glow 2.5s ease-out; }}
.bk-card, .bk-idea, .bk-game {{ transition: transform .15s ease, border-color .15s ease; }}
.bk-card:hover, .bk-idea:hover {{ transform: translateY(-2px); border-color: {LINE_STRONG}; }}
@keyframes bk-pulse {{ 0%, 100% {{ opacity: 1; transform: scale(1); }}
  50% {{ opacity: .35; transform: scale(.7); }} }}
@keyframes bk-slide-in {{ from {{ opacity: 0; transform: translateY(-8px); }}
  to {{ opacity: 1; transform: none; }} }}
@keyframes bk-glow {{ 0% {{ background: rgba(0,186,124,.22); }} 100% {{ background: transparent; }} }}

/* the shot chart */
.bk-court {{ margin: 6px 0 14px; }}
.bk-court svg {{ display: block; width: 100%; height: auto; border-radius: 18px;
  background: #0B0D10; border: 1px solid {LINE}; }}
.bk-court-team {{ font-weight: 800; font-size: 26px; letter-spacing: .05em; }}
.bk-shot.fresh {{ animation: bk-shot-in .9s ease-out; transform-box: fill-box;
  transform-origin: center; }}
@keyframes bk-shot-in {{ 0% {{ transform: scale(2.6); opacity: 0; }}
  60% {{ transform: scale(.9); opacity: 1; }} 100% {{ transform: scale(1); }} }}

/* no stray blue: links and alert boxes follow the black palette */
.stApp a, .stApp a:visited {{ color: {TEXT}; text-decoration: underline; text-decoration-color: {LINE_STRONG}; }}
.stApp a:hover {{ color: {BUTTON}; text-decoration-color: {BUTTON}; }}
[data-testid="stAlertContainer"] {{
  background: {RAISED}; border: 1px solid {LINE}; border-radius: 16px; color: {TEXT};
}}
[data-testid="stAlertContainer"] svg {{ color: {MUTED}; fill: {MUTED}; }}

/* narrow screens. These come last so they win over the rules above. */
@media (max-width: 900px) {{
  [data-testid="stColumn"]:has(.st-key-slip-panel) {{
    position: static; max-height: none; overflow: visible;
  }}
}}
@media (max-width: 640px) {{
  .stTabs [role="tablist"] {{ padding: 3px; gap: 0; }}
  .stTabs [data-testid="stTab"] {{ padding: 7px 9px; font-size: .78rem; }}
  .bk-appbar-name {{ font-size: 1.1rem; }}
  .bk-appbar-logo {{ width: 28px; height: 28px; }}
  .bk-strip-cell {{ flex-basis: 40%; padding: 10px 12px; }}
  .bk-strip-cell b {{ font-size: 1.25rem; }}
  .bk-hero {{ padding: 14px 10px; gap: 6px; }}
  .bk-hero-logo {{ width: 40px; height: 40px; }}
  .bk-hero-score {{ font-size: 2.2rem; }}
  .bk-hero-clock {{ font-size: .8rem; }}
  .block-container {{ padding: 3.2rem .8rem 5rem; }}
  [class*="st-key-browse-list"] button {{ padding: .2rem .15rem; min-height: 2.2rem; }}
  [class*="st-key-browse-list"] button p {{ font-size: .72rem; line-height: 1.15; }}
  [class*="st-key-browse-list"] [data-testid="stImage"] img {{ width: 30px !important; }}
  [class*="st-key-browse-list"] [data-testid="stMarkdownContainer"] p {{ font-size: .8rem; line-height: 1.2; }}
  .bk-slip-big {{ font-size: 1.7rem; }}
  .bk-slip-row {{ gap: 16px; }}
  .stTabs [data-baseweb="tab"] {{ padding: 12px 10px; }}
  /* all six tabs fit on one row, so none hides behind the scroll arrow */
  [role="tablist"] {{ gap: 0 !important; }}
  [data-testid="stTab"] {{ padding: 8px 8px; font-size: .8rem; }}
  [data-testid="stTab"] [role="img"] {{ display: none !important; }}
  /* hover-only extras: tiny targets nobody can use with a thumb */
  [data-testid="stElementToolbar"], [data-testid="stHeaderActionElements"] {{ display: none !important; }}
}}
/* anything a thumb taps is at least 44px tall (phones, and touch tablets) */
@media (max-width: 900px), (pointer: coarse) {{
  [data-testid="stTab"] {{ min-height: 44px; }}
  [data-testid="stBaseButton-pills"], [data-testid="stBaseButton-pillsActive"],
  [data-testid="stButtonGroup"] button {{ min-height: 44px; }}
  .stButton button, .stDownloadButton button, [data-testid^="stBaseButton"] {{ min-height: 44px; }}
  [data-baseweb="input"], [data-baseweb="base-input"] {{ min-height: 44px; }}
  [class*="st-key-browse-list"] button {{ min-height: 44px; }}
  [data-testid="stRadio"] label {{ min-height: 44px; align-items: center; }}
  [data-testid="stNumberInput"] button {{ min-height: 44px; min-width: 44px; }}
  [data-baseweb="select"] > div {{ min-height: 44px; }}
  [data-testid="stExpander"] summary {{ min-height: 44px; }}
}}
</style>
"""
