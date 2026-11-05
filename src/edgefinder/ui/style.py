"""The app's look: a sportsbook-style dark theme with bet-slip cards.

Inspired by the layout of betting apps (blue accents, rounded cards, odds
in a pill) without borrowing any brand's name or logo. Streamlit's own
theme is set in .streamlit/config.toml; this adds the pieces it can't style.

Every piece of text that comes from data (player names, game text) is
escaped before it goes into HTML.
"""

import re
from html import escape

import streamlit as st

from .team_colors import rgba

BLUE = "#1493FF"
GREEN = "#1DB954"
AMBER = "#F5B83D"
RED = "#F0524F"
MUTED = "#8FA0BC"

CSS = f"""
<style>
.block-container {{ padding-top: 3.4rem; padding-bottom: 5rem; max-width: 1180px; }}
h1, h2, h3, h4 {{ letter-spacing: -0.01em; }}
h2 {{ font-size: 1.7rem !important; }}
h4 {{ font-size: 1.05rem !important; font-weight: 800 !important; margin-top: .6rem; }}

/* the app is its own thing: no sidebar, no deploy bar */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] {{ display: none !important; }}

/* long documents inside the app: smaller headings than a web page would use */
.st-key-about h1 {{ font-size: 1.7rem !important; }}
.st-key-about h2 {{ font-size: 1.3rem !important; margin-top: 1.4rem; }}
.st-key-about h3 {{ font-size: 1.05rem !important; }}
.st-key-about table {{ font-size: 0.88rem; }}

/* the slip summary stays in view while you scroll past the list */
[data-testid="stLayoutWrapper"]:has(> .st-key-slip-bar) {{
  position: sticky; top: 3.5rem; z-index: 60; background: #0B1220;
}}
.st-key-slip-bar {{ padding: 8px 0 6px; border-bottom: 1px solid #22304d; }}
/* rows of buttons stay on one line, even on a phone */
.st-key-browse-list [data-testid="stHorizontalBlock"],
.st-key-slip-panel [data-testid="stHorizontalBlock"],
.st-key-slip-bar [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: .5rem; }}
.st-key-browse-list [data-testid="stColumn"],
.st-key-slip-panel [data-testid="stColumn"],
.st-key-slip-bar [data-testid="stColumn"] {{ min-width: 0 !important; }}
.bk-note {{
  padding: 10px 14px; border-radius: 12px; font-size: 0.85rem; color: #cfe3ff;
  background: rgba(20,147,255,0.08); border: 1px solid rgba(20,147,255,0.28); margin: 8px 0;
}}
.bk-footer {{
  margin-top: 2.5rem; padding-top: 14px; border-top: 1px solid #22304d;
  color: {MUTED}; font-size: 0.78rem; line-height: 1.5;
}}
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
.bk-team {{ border-left: 3px solid transparent; padding-left: 8px; }}
.bk-tiny-logo {{ width: 18px; height: 18px; object-fit: contain; margin-right: 7px;
  vertical-align: -3px; }}
.bk-title {{ display: flex; align-items: center; }}
.bk-banner {{
  display: flex; align-items: center; gap: 18px; padding: 16px 18px; border-radius: 18px;
  border: 1px solid #22304d; margin-bottom: 12px;
}}
.bk-banner {{ align-items: flex-end; padding-bottom: 0; overflow: hidden; }}
.bk-banner-photo {{ height: 138px; width: auto; flex: none; display: block; }}
.bk-banner-text {{ padding-bottom: 18px; }}
.bk-banner-name {{ font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.1; }}
.bk-banner-sub {{ color: #cfd9ea; margin-top: 6px; display: flex; align-items: center;
  font-size: 0.95rem; }}
.bk-tile {{
  background: #131d33; border: 1px solid #22304d; border-top: 3px solid {BLUE};
  border-radius: 12px; padding: 12px 8px; text-align: center;
}}
.bk-tile-value {{ font-size: 1.7rem; font-weight: 800; line-height: 1.1; }}
.bk-tile-label {{ color: {MUTED}; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; margin-top: 4px; }}
/* prices are pills, like a betting app's odds buttons */
.st-key-browse-list button {{ border-radius: 999px; }}
.bk-teams {{ flex: 1; }}
.bk-team {{ display: flex; align-items: center; gap: 10px; padding: 3px 0; color: {MUTED}; }}
.bk-team.lead {{ color: #F4F7FB; font-weight: 700; }}
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
.bk-cmp-val.lead {{ color: #F4F7FB; font-weight: 800; }}
.bk-cmp-bar {{ display: flex; height: 7px; border-radius: 5px; overflow: hidden; margin-top: 4px;
  background: #0b1220; gap: 2px; }}
.bk-cmp-bar .away {{ background: {BLUE}; }}
.bk-cmp-bar .home {{ background: {AMBER}; }}
.bk-leader {{ display: flex; align-items: center; gap: 12px; padding: 8px 10px; margin: 6px 0;
  background: #131d33; border: 1px solid #22304d; border-radius: 12px; }}
.bk-photo.small {{ width: 54px; height: 44px; }}
.bk-leader-stat {{ text-align: right; flex: none; }}
.bk-leader-stat b {{ font-size: 1.3rem; display: block; line-height: 1.1; }}
.bk-leader-stat span {{ color: {MUTED}; font-size: 0.72rem; }}
.bk-empty {{
  text-align: center; padding: 28px 16px; border: 1.5px dashed #33425f; border-radius: 14px;
}}
.bk-empty-title {{ font-weight: 700; margin-bottom: 4px; }}
.bk-feed {{ padding: 8px 0; border-bottom: 1px solid #1d2a45; }}
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
}}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def choose(label: str, options: list, key: str, format_func=str, on_change=None):
    """Pick one of a few options as tappable chips instead of a dropdown.

    Always returns an option: the first until the user picks, and the last pick
    if they tap it again to clear it. With only one option there is nothing to
    choose, so it is shown as plain text, and the value is still stored under
    `key` so other views can read it."""
    if len(options) == 1:
        st.session_state[key] = options[0]
        st.caption(f"**{label}:** {format_func(options[0])}")
        return options[0]
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)
    picked = st.pills(label, options, selection_mode="single", default=options[0], key=key,
                      format_func=format_func, on_change=on_change)
    return options[0] if picked is None else picked


def odds_pill(text: str, kind: str = "") -> str:
    return f'<div class="bk-pill {escape(kind)}">{escape(text)}</div>'


_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def _hex(color: str) -> str:
    """The color if it is a plain #RRGGBB value, else empty, so a bad value can
    never end up inside a style attribute."""
    return color if _HEX.fullmatch(color or "") else ""


def _logo(url: str, css: str = "bk-tiny-logo") -> str:
    return f'<img class="{css}" src="{escape(url, quote=True)}" alt="">' if url else ""


def leg_card(photo_url: str, title: str, subtitle: str, pill_text: str, *, kind: str = "",
             progress: float | None = None, detail: str = "", compact: bool = False,
             accent: str = "", logo: str = "") -> str:
    """One bet as a card: the player's cutout, the bet, small print, an optional
    progress bar, and a pill on the right (the odds, or a status). `kind` colours
    the card and pill: hit, alive, missed, neutral, or empty for the default blue.
    `compact` shrinks it to fit a narrow column such as the slip. `accent` is
    the player's team color, shown along the card edge, and `logo` is the team's
    logo, shown beside his name. The player stands on the card itself, with no
    shape behind him."""
    bar = ""
    if progress is not None:
        width = round(max(0.0, min(1.0, progress)) * 100)
        bar = f'<div class="bk-bar"><div style="width:{width}%"></div></div>'
    more = f'<div class="bk-sub">{escape(detail)}</div>' if detail else ""
    size = " compact" if compact else ""
    color = _hex(accent)
    edge = f' style="border-left-color:{color}"' if color and not kind else ""
    return (
        f'<div class="bk-card {escape(kind)}{size}"{edge}>'
        f'<img class="bk-photo" src="{escape(photo_url, quote=True)}" alt="">'
        f'<div class="bk-body"><div class="bk-title">{_logo(logo)}{escape(title)}</div>'
        f'<div class="bk-sub">{escape(subtitle)}</div>{more}{bar}</div>'
        f'{odds_pill(pill_text, kind)}</div>'
    )


def player_banner(name: str, photo_url: str, logo: str, subtitle: str, color: str) -> str:
    """The top of a player's page: his cutout standing on a wash of the team's
    color, his name large, and the team's logo and details beside him."""
    tint = _hex(color) or BLUE
    return (
        f'<div class="bk-banner" style="background:linear-gradient(120deg,{rgba(tint, 0.55)},'
        f'{rgba(tint, 0.08)} 70%);border-color:{rgba(tint, 0.5)}">'
        f'<img class="bk-banner-photo" src="{escape(photo_url, quote=True)}" alt="">'
        f'<div class="bk-banner-text"><div class="bk-banner-name">{escape(name)}</div>'
        f'<div class="bk-banner-sub">{_logo(logo)}{escape(subtitle)}</div></div></div>'
    )


def stat_tile(label: str, value: str, color: str = "") -> str:
    """One big number with its label, for a row of season averages."""
    tint = _hex(color) or BLUE
    return (f'<div class="bk-tile" style="border-top-color:{tint}">'
            f'<div class="bk-tile-value">{escape(value)}</div>'
            f'<div class="bk-tile-label">{escape(label)}</div></div>')


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
              home_score: int, status: str, state: str, away_color: str = "",
              home_color: str = "") -> str:
    """A scoreboard card with both teams' logos and colors. `state` is live,
    final or upcoming; scores are hidden before tip-off."""
    started = state != "upcoming"

    def row(code: str, logo: str, score: int, other: int, color: str) -> str:
        shown = str(score) if started else "–"
        lead = " lead" if started and score > other else ""
        tint = _hex(color)
        edge = f' style="border-left-color:{tint}"' if tint else ""
        return (f'<div class="bk-team{lead}"{edge}>{_logo(logo, "bk-logo")}'
                f'<span>{escape(code)}</span><b>{escape(shown)}</b></div>')

    return (
        f'<div class="bk-game {escape(state)}"><div class="bk-teams">'
        f'{row(away, away_logo, away_score, home_score, away_color)}'
        f'{row(home, home_logo, home_score, away_score, home_color)}'
        f'</div><div class="bk-game-status">{escape(status)}</div></div>'
    )


def compare_bar(label: str, away_text: str, home_text: str, away_share: float,
                ahead: str, away_color: str = "", home_color: str = "") -> str:
    """One team-stat row: the number for each side, the label between them, and
    a bar split by their shares, in each team's color. The side that is ahead
    is highlighted."""
    width = round(max(0.0, min(1.0, away_share)) * 100)
    away_bar = f' style="width:{width}%;background:{_hex(away_color) or BLUE}"'
    home_bar = f' style="width:{100 - width}%;background:{_hex(home_color) or AMBER}"'
    return (
        f'<div class="bk-cmp"><div class="bk-cmp-top">'
        f'<span class="bk-cmp-val {"lead" if ahead == "away" else ""}">{escape(away_text)}</span>'
        f'<span class="bk-cmp-label">{escape(label)}</span>'
        f'<span class="bk-cmp-val {"lead" if ahead == "home" else ""}">{escape(home_text)}</span>'
        f'</div><div class="bk-cmp-bar"><div class="away"{away_bar}></div>'
        f'<div class="home"{home_bar}></div></div></div>'
    )


def leader_card(photo_url: str, name: str, team: str, stat: str, value: int,
                accent: str = "", logo: str = "") -> str:
    color = _hex(accent)
    edge = f' style="border-left:4px solid {color}"' if color else ""
    return (
        f'<div class="bk-leader"{edge}><img class="bk-photo small" '
        f'src="{escape(photo_url, quote=True)}" alt="">'
        f'<div class="bk-body"><div class="bk-title">{_logo(logo)}{escape(name)}</div>'
        f'<div class="bk-sub">{escape(team)}</div></div>'
        f'<div class="bk-leader-stat"><b>{value}</b><span>{escape(stat)}</span></div></div>'
    )


def dots(filled: int, total: int = 7) -> str:
    """'●●●○○○○' for timeouts left."""
    filled = max(0, min(total, filled))
    return "●" * filled + "○" * (total - filled)


def notice(text: str) -> str:
    """A slim heads-up, quieter than a warning box."""
    return f'<div class="bk-note">{escape(text)}</div>'


def footer(lines: list[str]) -> str:
    return f'<div class="bk-footer">{"<br>".join(escape(line) for line in lines)}</div>'


def empty_slip(title: str, hint: str) -> str:
    return (f'<div class="bk-empty"><div class="bk-empty-title">{escape(title)}</div>'
            f'<div class="bk-sub">{escape(hint)}</div></div>')


def feed_item(clock: str, text: str, score: str) -> str:
    return (
        f'<div class="bk-feed"><span class="bk-feed-time">{escape(clock)}</span>'
        f'<span class="bk-feed-score">{escape(score)}</span>'
        f'<div>{escape(text)}</div></div>'
    )
