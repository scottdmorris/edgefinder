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
.block-container {{ padding-top: 3.4rem; padding-bottom: 5rem; max-width: 1180px; }}
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
.stTabs [data-baseweb="tab-list"] {{ gap: 0; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 500; padding: 14px 16px; color: {MUTED}; }}
.stTabs [aria-selected="true"] {{ color: {TEXT}; font-weight: 800; }}
[data-testid="stTab"] {{ font-weight: 500; color: {MUTED}; }}
[data-testid="stTab"][aria-selected="true"] {{ color: {TEXT}; font-weight: 800; }}

/* heads-up boxes keep the black look: no default blue/yellow/green fills */
[data-testid="stAlert"] {{ background: {RAISED} !important; border: 1px solid {LINE};
  border-radius: 16px; color: {TEXT}; }}

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
.st-key-browse-list [data-testid="stHorizontalBlock"],
.st-key-slip-panel [data-testid="stHorizontalBlock"],
.st-key-slip-bar [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: .5rem; }}
.st-key-browse-list [data-testid="stColumn"],
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
.bk-team b {{ margin-left: auto; font-size: 1.05rem; }}
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
.bk-feed {{ padding: 8px 0; border-bottom: 1px solid {LINE}; }}
.bk-feed:last-child {{ border-bottom: 0; }}
.bk-feed-time {{ color: {MUTED}; font-size: 0.78rem; font-weight: 700; }}
.bk-feed-score {{ color: {MUTED}; font-size: 0.78rem; float: right; }}

/* narrow screens. These come last so they win over the rules above. */
@media (max-width: 900px) {{
  [data-testid="stColumn"]:has(.st-key-slip-panel) {{
    position: static; max-height: none; overflow: visible;
  }}
}}
@media (max-width: 640px) {{
  .block-container {{ padding: 3.2rem .8rem 5rem; }}
  .st-key-browse-list button {{ padding: .2rem .15rem; min-height: 2.2rem; }}
  .st-key-browse-list button p {{ font-size: .72rem; line-height: 1.15; }}
  .st-key-browse-list [data-testid="stImage"] img {{ width: 30px !important; }}
  .st-key-browse-list [data-testid="stMarkdownContainer"] p {{ font-size: .8rem; line-height: 1.2; }}
  .bk-slip-big {{ font-size: 1.7rem; }}
  .bk-slip-row {{ gap: 16px; }}
  .stTabs [data-baseweb="tab"] {{ padding: 12px 10px; }}
  /* all six tabs fit on one row, so none hides behind the scroll arrow */
  [role="tablist"] {{ gap: 0 !important; }}
  [data-testid="stTab"] {{ padding: 8px 8px; font-size: .8rem; }}
  /* hover-only extras: tiny targets nobody can use with a thumb */
  [data-testid="stElementToolbar"], [data-testid="stHeaderActionElements"] {{ display: none !important; }}
}}
/* anything a thumb taps is at least 44px tall (phones, and touch tablets) */
@media (max-width: 900px), (pointer: coarse) {{
  [data-testid="stTab"] {{ min-height: 44px; }}
  [data-testid="stBaseButton-pills"], [data-testid="stBaseButton-pillsActive"] {{ min-height: 44px; }}
  .stButton > button, .stDownloadButton > button {{ min-height: 44px; }}
  .st-key-browse-list button {{ min-height: 44px; }}
  [data-testid="stRadio"] label {{ min-height: 44px; align-items: center; }}
  [data-testid="stNumberInput"] button {{ min-height: 44px; min-width: 44px; }}
  [data-baseweb="select"] > div {{ min-height: 44px; }}
  [data-testid="stExpander"] summary {{ min-height: 44px; }}
}}
</style>
"""
