"""The app's look: a sportsbook-style dark theme with bet-slip cards.

Inspired by the layout of betting apps (blue accents, rounded cards, odds
in a pill) without borrowing any brand's name or logo. Streamlit's own
theme is set in .streamlit/config.toml; this adds the pieces it can't style.

Every piece of text that comes from data (player names, game text) is
escaped before it goes into HTML.
"""

from html import escape

import streamlit as st

BLUE = "#1493FF"
GREEN = "#1DB954"
AMBER = "#F5B83D"
RED = "#F0524F"
MUTED = "#8FA0BC"

CSS = f"""
<style>
.block-container {{ padding-top: 2.2rem; max-width: 880px; }}
h1, h2, h3, h4 {{ letter-spacing: -0.01em; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid #22304d; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 700; padding: 10px 14px; }}
.stTabs [aria-selected="true"] {{ color: {BLUE}; }}
[data-testid="stMetric"] {{
  background: #131d33; border: 1px solid #22304d; border-radius: 14px; padding: 14px 16px;
}}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 0.8rem; }}
[data-testid="stExpander"] {{ border: 1px solid #22304d; border-radius: 12px; }}
.stButton > button[kind="primary"] {{ background: {BLUE}; border: 0; font-weight: 700; }}

.bk-card {{
  display: flex; align-items: center; gap: 14px; padding: 12px 14px; margin: 8px 0;
  background: #131d33; border: 1px solid #22304d; border-left: 4px solid {BLUE};
  border-radius: 14px;
}}
.bk-card.hit {{ border-left-color: {GREEN}; }}
.bk-card.alive {{ border-left-color: {AMBER}; }}
.bk-card.missed {{ border-left-color: {RED}; }}
.bk-photo {{
  width: 56px; height: 56px; border-radius: 50%; object-fit: cover; object-position: top;
  background: #0b1220; flex: none;
}}
.bk-body {{ flex: 1; min-width: 0; }}
.bk-title {{ font-weight: 700; font-size: 1rem; line-height: 1.25; }}
.bk-sub {{ color: {MUTED}; font-size: 0.82rem; margin-top: 2px; }}
.bk-bar {{ height: 8px; border-radius: 6px; background: #0b1220; margin-top: 8px; overflow: hidden; }}
.bk-bar > div {{ height: 100%; border-radius: 6px; background: {BLUE}; }}
.bk-card.hit .bk-bar > div {{ background: {GREEN}; }}
.bk-card.alive .bk-bar > div {{ background: {AMBER}; }}
.bk-card.missed .bk-bar > div {{ background: {RED}; }}
.bk-pill {{
  flex: none; min-width: 64px; text-align: center; padding: 8px 12px; border-radius: 10px;
  font-weight: 800; font-size: 0.95rem; border: 1.5px solid {BLUE}; color: {BLUE};
  background: rgba(20,147,255,0.10);
}}
.bk-pill.hit {{ border-color: {GREEN}; color: {GREEN}; background: rgba(29,185,84,0.12); }}
.bk-pill.alive {{ border-color: {AMBER}; color: {AMBER}; background: rgba(245,184,61,0.12); }}
.bk-pill.missed {{ border-color: {RED}; color: {RED}; background: rgba(240,82,79,0.12); }}
.bk-pill.neutral {{ border-color: #33425f; color: {MUTED}; background: transparent; }}

.bk-slip {{
  margin: 14px 0; padding: 16px 18px; border-radius: 16px;
  background: linear-gradient(135deg, #0f2a52 0%, #123a73 100%); border: 1px solid #1b4d93;
}}
.bk-slip-head {{ color: #cfe3ff; font-size: 0.8rem; font-weight: 700; letter-spacing: 0.06em; }}
.bk-slip-big {{ font-size: 2rem; font-weight: 800; line-height: 1.15; margin-top: 4px; }}
.bk-slip-row {{ display: flex; gap: 28px; flex-wrap: wrap; margin-top: 10px; }}
.bk-slip-row > div > span {{ display: block; }}
.bk-slip-k {{ color: #9fc3f5; font-size: 0.75rem; }}
.bk-slip-v {{ font-weight: 700; font-size: 1.05rem; }}
.bk-game {{
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; margin: 6px 0; background: #131d33; border: 1px solid #22304d;
  border-radius: 14px;
}}
.bk-game.live {{ border-color: {GREEN}; }}
.bk-teams {{ flex: 1; }}
.bk-team {{ display: flex; align-items: center; gap: 10px; padding: 3px 0; color: {MUTED}; }}
.bk-team.lead {{ color: #F4F7FB; font-weight: 700; }}
.bk-team b {{ margin-left: auto; font-size: 1.05rem; }}
.bk-logo {{ width: 26px; height: 26px; object-fit: contain; flex: none; }}
.bk-game-status {{ font-size: 0.78rem; font-weight: 700; color: {MUTED}; text-align: right; flex: none; }}
.bk-game.live .bk-game-status {{ color: {GREEN}; }}
.bk-feed {{ padding: 8px 0; border-bottom: 1px solid #1d2a45; }}
.bk-feed:last-child {{ border-bottom: 0; }}
.bk-feed-time {{ color: {MUTED}; font-size: 0.78rem; font-weight: 700; }}
.bk-feed-score {{ color: {MUTED}; font-size: 0.78rem; float: right; }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def odds_pill(text: str, kind: str = "") -> str:
    return f'<div class="bk-pill {escape(kind)}">{escape(text)}</div>'


def leg_card(photo_url: str, title: str, subtitle: str, pill_text: str, *, kind: str = "",
             progress: float | None = None, detail: str = "") -> str:
    """One bet as a card: photo, bet, small print, an optional progress bar,
    and a pill on the right (the odds, or a status). `kind` colours the card
    and pill: hit, alive, missed, neutral, or empty for the default blue."""
    bar = ""
    if progress is not None:
        width = round(max(0.0, min(1.0, progress)) * 100)
        bar = f'<div class="bk-bar"><div style="width:{width}%"></div></div>'
    more = f'<div class="bk-sub">{escape(detail)}</div>' if detail else ""
    return (
        f'<div class="bk-card {escape(kind)}">'
        f'<img class="bk-photo" src="{escape(photo_url, quote=True)}" alt="">'
        f'<div class="bk-body"><div class="bk-title">{escape(title)}</div>'
        f'<div class="bk-sub">{escape(subtitle)}</div>{more}{bar}</div>'
        f'{odds_pill(pill_text, kind)}</div>'
    )


def slip_summary(head: str, big: str, facts: list[tuple[str, str]]) -> str:
    """The highlighted box at the bottom of a slip: a headline number and a
    row of labelled facts."""
    items = "".join(
        f'<div><span class="bk-slip-k">{escape(label)}</span>'
        f'<span class="bk-slip-v">{escape(value)}</span></div>' for label, value in facts)
    return (
        f'<div class="bk-slip"><div class="bk-slip-head">{escape(head)}</div>'
        f'<div class="bk-slip-big">{escape(big)}</div>'
        f'<div class="bk-slip-row">{items}</div></div>'
    )


def game_card(away: str, home: str, away_logo: str, home_logo: str, away_score: int,
              home_score: int, status: str, state: str) -> str:
    """A scoreboard card with both teams' logos. `state` is live, final or
    upcoming; scores are hidden before tip-off."""
    started = state != "upcoming"

    def row(code: str, logo: str, score: int, other: int) -> str:
        shown = str(score) if started else "–"
        lead = " lead" if started and score > other else ""
        image = f'<img class="bk-logo" src="{escape(logo, quote=True)}" alt="">' if logo else ""
        return (f'<div class="bk-team{lead}">{image}<span>{escape(code)}</span>'
                f'<b>{escape(shown)}</b></div>')

    return (
        f'<div class="bk-game {escape(state)}"><div class="bk-teams">'
        f'{row(away, away_logo, away_score, home_score)}'
        f'{row(home, home_logo, home_score, away_score)}'
        f'</div><div class="bk-game-status">{escape(status)}</div></div>'
    )


def feed_item(clock: str, text: str, score: str) -> str:
    return (
        f'<div class="bk-feed"><span class="bk-feed-time">{escape(clock)}</span>'
        f'<span class="bk-feed-score">{escape(score)}</span>'
        f'<div>{escape(text)}</div></div>'
    )
