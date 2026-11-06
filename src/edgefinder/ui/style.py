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
from .theme import AMBER, BLUE, CSS, GREEN, MUTED, RED  # noqa: F401


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def choose(label: str, options: list, key: str, format_func=str, on_change=None, default=None):
    """Pick one of a few options as tappable chips instead of a dropdown.

    Always returns an option: `default` (the first if none is given) until the
    user picks, and that default again if they tap their pick to clear it. With
    only one option there is nothing to choose, so it is shown as plain text,
    and the value is still stored under `key` so other views can read it."""
    if len(options) == 1:
        st.session_state[key] = options[0]
        st.caption(f"**{label}:** {format_func(options[0])}")
        return options[0]
    start = options[0] if default is None or default not in options else default
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)
    picked = st.pills(label, options, selection_mode="single", default=start, key=key,
                      format_func=format_func, on_change=on_change)
    return start if picked is None else picked


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
             accent: str = "", logo: str = "", flash: bool = False) -> str:
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
    size = (" compact" if compact else "") + (" flash" if flash else "")
    color = _hex(accent)
    edge = f' style="border-left-color:{color}"' if color and not kind else ""
    return (
        f'<div class="bk-card {escape(kind)}{size}"{edge}>'
        f'<img class="bk-photo" src="{escape(photo_url, quote=True)}" alt="">'
        f'<div class="bk-body"><div class="bk-title">{_logo(logo)}{escape(title)}</div>'
        f'<div class="bk-sub">{escape(subtitle)}</div>{more}{bar}</div>'
        f'{odds_pill(pill_text, kind)}</div>'
    )


def idea_card(legs: list[tuple[str, str, str, str]], chance: str, pays: str) -> str:
    """A suggested slip: one row per leg (photo, player, bet, odds), then the chance
    and payout. Each leg is (photo_url, player, bet, odds)."""
    rows = "".join(
        f'<div class="bk-leg"><img class="bk-photo small" src="{escape(photo, quote=True)}" '
        f'alt=""><div class="bk-body"><div class="bk-title">{escape(name)}</div>'
        f'<div class="bk-sub">{escape(bet)}</div></div>{odds_pill(odds)}</div>'
        for photo, name, bet, odds in legs)
    return (f'<div class="bk-idea">{rows}<div class="bk-idea-foot">'
            f'<b>{escape(chance)}</b> to hit · <b>{escape(pays)}</b> back on $1</div></div>')


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
              home_color: str = "", away_pop: int = 0, home_pop: int = 0) -> str:
    """A scoreboard card with both teams' logos and colors. `state` is live,
    final or upcoming; scores are hidden before tip-off. `away_pop` and `home_pop` are
    points a team just scored: its score flashes and a "+3" floats up beside it."""
    started = state != "upcoming"

    def row(code: str, logo: str, score: int, other: int, color: str, pop: int) -> str:
        shown = str(score) if started else "–"
        lead = " lead" if started and score > other else ""
        scored = " scored" if started and pop > 0 else ""
        tint = _hex(color)
        edge = f' style="border-left-color:{tint}"' if tint else ""
        burst = (f'<span class="bk-pop p{min(int(pop), 3)}">+{int(pop)}</span>'
                 if started and pop > 0 else "")
        return (f'<div class="bk-team{lead}{scored}"{edge}>{_logo(logo, "bk-logo")}'
                f'<span>{escape(code)}</span><b>{escape(shown)}</b>{burst}</div>')

    return (
        f'<div class="bk-game {escape(state)}"><div class="bk-teams">'
        f'{row(away, away_logo, away_score, home_score, away_color, away_pop)}'
        f'{row(home, home_logo, home_score, away_score, home_color, home_pop)}'
        f'</div><div class="bk-game-status">{escape(status)}</div></div>'
    )


def game_hero(away: str, home: str, away_logo: str, home_logo: str, away_score: int,
              home_score: int, status: str, state: str, away_color: str = "",
              home_color: str = "", away_pop: int = 0, home_pop: int = 0,
              away_note: str = "", home_note: str = "") -> str:
    """The open game, big: each team's logo, code and score in its colors, the clock in the
    middle, and a small line under each team (timeouts, fouls). Scores are hidden before
    tip-off. A team that just scored flashes and shows "+2" / "+3"."""
    started = state != "upcoming"
    tint_away, tint_home = _hex(away_color) or BLUE, _hex(home_color) or AMBER

    def side(code, logo, score, other, pop, note, where):
        shown = str(score) if started else "–"
        lead = " lead" if started and score > other else ""
        scored = " scored" if started and pop > 0 else ""
        burst = (f'<span class="bk-pop p{min(int(pop), 3)}">+{int(pop)}</span>'
                 if started and pop > 0 else "")
        mark = _logo(logo, "bk-hero-logo") if logo else ""
        return (f'<div class="bk-hero-team {where}{lead}{scored}">{mark}'
                f'<div class="bk-hero-code">{escape(code)}</div>'
                f'<div class="bk-hero-score">{escape(shown)}{burst}</div>'
                f'<div class="bk-hero-note">{escape(note)}</div></div>')

    badge = {"live": "LIVE", "final": "FINAL"}.get(state, "")
    return (
        f'<div class="bk-hero {escape(state)}" style="background:linear-gradient(90deg,'
        f'{rgba(tint_away, 0.30)},{rgba(tint_away, 0.0)} 38%,{rgba(tint_home, 0.0)} 62%,'
        f'{rgba(tint_home, 0.30)})">'
        f'{side(away, away_logo, away_score, home_score, away_pop, away_note, "away")}'
        f'<div class="bk-hero-mid"><div class="bk-hero-badge">{escape(badge)}</div>'
        f'<div class="bk-hero-clock">{escape(status)}</div></div>'
        f'{side(home, home_logo, home_score, away_score, home_pop, home_note, "home")}</div>'
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


def feed_item(clock: str, text: str, score: str, fresh: bool = False, color: str = "") -> str:
    """One play. A `fresh` play (new since the last refresh) slides in and glows; `color` is
    the team's, shown on its edge."""
    tint = _hex(color)
    edge = f' style="border-left-color:{tint}"' if tint else ""
    return (
        f'<div class="bk-feed{" new" if fresh else ""}"{edge}>'
        f'<span class="bk-feed-time">{escape(clock)}</span>'
        f'<span class="bk-feed-score">{escape(score)}</span>'
        f'<div>{escape(text)}</div></div>'
    )
