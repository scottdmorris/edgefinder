"""Parlay builder: pick bets from the day's lines and see what the slip is
really worth.

Read-only: it works from what the scheduled jobs recorded and never calls
the Odds API. A bet's chance is the model's number blended 30/70 toward the
market's, and bets from the same game are priced with the correlations
measured from history.

Layout, like a betting app: browse on the left, and the slip on the right,
which stays in view while you scroll. Every change to the slip goes through
one callback, so adding, removing and replacing can't disagree.
"""

import datetime as dt

import altair as alt
import pandas as pd
import streamlit as st

from ..betting import correlated
from ..data import nba_injuries, nba_live, nba_players, nba_stats
from ..models import nba_stat_model
from ..tracking import nba_alt, nba_paper, nba_parlay, nba_view, price_gaps
from . import shared, style, team_colors

DEFAULT_STAKE = 10.0
LEGS_KEY = "parlay_legs"
IDEAS_SHOWN = 3
GAPS_SHOWN = 5
HOW_TO = (
    "**1.** Pick a game day and a projection.  **2.** Tap a price to add a bet to your "
    "slip (tap it again to remove it).  **3.** Read the slip: how likely it is that "
    "every bet hits, and whether the payout is worth that risk."
)
GLOSSARY = """
- **Parlay / slip:** several bets tied together. Every one has to hit to get paid.
- **Leg:** one bet inside the parlay.
- **Over 24.5 points:** the player scores 25 or more. **25+ points** is the same idea.
- **Chance it hits:** how likely the model thinks it is. *1 in 37* is the same number
  said another way.
- **Odds that break even:** the payout at which the bet is a coin flip between
  winning and losing money over time. If the book pays more than that, the bet has
  value; if it pays less, it doesn't.
- **Expected profit per \\$1:** what you'd win or lose on average per dollar if you
  made this exact bet again and again, *assuming the model is right*. Long shots
  can show big expected profits while still almost never hitting.
- **Average result at this stake:** the same number scaled to what you typed in.
  It is an average over many repeats, not what happens on one bet.
- **Projection:** the model's guess at how many points a player scores. Neither
  projection has been tested against real results yet.
"""


def render() -> None:
    ledger = nba_paper.load_ledger()
    if ledger.empty:
        st.info("No lines recorded yet. The scheduled job fills this in once "
                "tonight's lines are posted.")
        return
    st.subheader("Build a parlay")
    date = style.choose("Game day", nba_view.game_dates(ledger), "parlay_date",
                        on_change=_clear_slip)
    found = nba_parlay.sources(ledger, date)
    if not found:
        st.info("No lines were recorded on that day.")
        return
    book = style.choose("Prices", nba_parlay.books_on(found), "parlay_book",
                        format_func=lambda b: BOOK_NAMES.get(b, b), on_change=_clear_slip)
    version = style.choose("Model", nba_parlay.model_versions(found, book), "parlay_model",
                           format_func=nba_parlay.short_model_name, on_change=_clear_slip)
    with st.expander("How this works"):
        st.markdown(HOW_TO)
        st.markdown(GLOSSARY)
        st.caption(nba_parlay.model_name(version) + ". A stat this model didn't price uses "
                   "the Simple one.")
    if book == "kalshi":
        st.markdown(style.notice("Kalshi prices are before fees, and its markets are thin."),
                    unsafe_allow_html=True)

    candidates = nba_parlay.all_candidates(ledger, nba_alt.load_ledger(), date, version, book,
                                           found)
    if candidates.empty:
        st.info("This projection didn't price any lines on that day.")
        return
    current = _current_slip(candidates)
    _slip_bar(current)

    shown, single_game = _game_filter(candidates)
    browse, slip = st.columns([5, 4], gap="large")
    with browse:
        _price_gap_section(date, book, shown, candidates)
        _suggested(candidates, shown, single_game)
        _browse(shown, candidates, book)
        _search(candidates)
    with slip, st.container(key="slip-panel"):
        _slip_panel(candidates, current)


BOOK_NAMES = {"fanduel": "FanDuel", "kalshi": "Kalshi"}
ALL_GAMES = "All games"


# ---- the slip: every change goes through these three callbacks -------------------

def _clear_slip() -> None:
    """Bets are positions in the day's table, so they mean nothing after the
    day or projection changes."""
    st.session_state[LEGS_KEY] = []


def _toggle(index: int, candidates: pd.DataFrame) -> None:
    st.session_state[LEGS_KEY] = nba_parlay.toggle_leg(
        list(st.session_state.get(LEGS_KEY, [])), index,
        candidates["player_id"].astype(str) + "|" + candidates["stat_key"])


def _load(indices: list[int]) -> None:
    st.session_state[LEGS_KEY] = list(indices)


def _current_slip(candidates: pd.DataFrame):
    """(chosen bets, summary) for what's on the slip, or None if it's empty or
    can't be priced."""
    picked = [i for i in st.session_state.get(LEGS_KEY, []) if i in candidates.index]
    if not picked:
        return None
    chosen = candidates.loc[picked]
    try:
        return chosen, correlated.summarise(nba_parlay.to_legs(chosen, teams_by_player()))
    except ValueError as error:
        st.error(str(error))
        return None


def selected_legs() -> pd.DataFrame | None:
    """The bets currently picked in the builder, for other views to track.
    None when nothing is picked or the lines aren't available."""
    picked = st.session_state.get("parlay_legs")
    date, version = st.session_state.get("parlay_date"), st.session_state.get("parlay_model")
    book = st.session_state.get("parlay_book") or nba_parlay.BOOK
    ledger = nba_paper.load_ledger()
    if not picked or date is None or version is None or ledger.empty:
        return None
    found = nba_parlay.sources(ledger, date)
    if book not in found:
        return None
    candidates = nba_parlay.all_candidates(ledger, nba_alt.load_ledger(), date, version, book,
                                           found)
    chosen = candidates.reindex(picked).dropna(subset=["Leg"])
    return None if chosen.empty else chosen


def _slip_bar(current) -> None:
    """One line that stays pinned while you scroll, so the slip is never out of sight."""
    with st.container(key="slip-bar"):
        if current is None:
            st.markdown("🧾 **Your slip is empty.** Tap a price below to add a bet.")
            return
        chosen, summary = current
        stake = st.session_state.get("stake", DEFAULT_STAKE)
        wins = nba_parlay.stake_outcomes(stake, summary["decimal_odds"], summary["ev_per_unit"])
        word = "bet" if len(chosen) == 1 else "bets"
        left, right = st.columns([5, 2], vertical_alignment="center")
        left.markdown(
            f"🧾 **{len(chosen)} {word}** · \\${stake:,.0f} to win "
            f"**{nba_parlay.money(wins['profit_if_wins'])}** · "
            f"{summary['joint_probability'] * 100:.1f}% to hit")
        right.button("Clear", key="clear_top", on_click=_clear_slip, use_container_width=True)


# ---- browsing ---------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def _price_gaps(date: str) -> pd.DataFrame:
    """Every gap between FanDuel and Kalshi that day; remembered between taps."""
    return price_gaps.find_gaps(nba_paper.load_ledger(), nba_alt.load_ledger(), date)


def _price_gap_section(date: str, book: str, shown: pd.DataFrame,
                       candidates: pd.DataFrame) -> None:
    """Bets this book prices well above the other market's fair chance, biggest first."""
    gaps = _price_gaps(date)
    gaps = gaps[(gaps["Book"] == book) & gaps["Game"].isin(set(shown["Game"]))].head(GAPS_SHOWN)
    if gaps.empty:
        return
    other = "Kalshi" if book == "fanduel" else "FanDuel"
    st.markdown("#### Where the prices disagree")
    st.caption(f"Bets priced above {other}'s fair chance for the same thing. This is the other "
               "market's view, not our model's"
               + ("; Kalshi prices are before its fees" if book == "kalshi" else "")
               + ". Prices are from the last snapshot and may have moved.")
    slip = set(st.session_state.get(LEGS_KEY, []))
    short = {g: f"{r.away_abbr} @ {r.home_abbr}" for g, r in
             candidates.drop_duplicates("Game").set_index("Game").iterrows()}
    for position, row in gaps.iterrows():
        card, action = st.columns([4, 1], vertical_alignment="center")
        mine, theirs = BOOK_NAMES.get(book, book), row["Reference"]
        estimate = " (est.)" if row["How"] == "estimated" else ""
        card.markdown(style.leg_card(
            nba_parlay.headshot_url(row["player_id"]), row["Player"],
            f"{row['Bet']} pts · {shared.fmt_american(row['Odds'])} · "
            f"{short.get(row['Game'], row['Game'])}",
            f"+{row['Edge %']:.1f}%",
            detail=f"{theirs} {row['Reference %']:.0f}%{estimate} vs {mine}'s "
                   f"{row['Price says %']:.0f}%", compact=True),
            unsafe_allow_html=True)
        index = price_gaps.candidate_index(candidates, row)
        if index is not None:
            action.button("✓ On slip" if index in slip else "Add", key=f"gap_{position}",
                          type="primary" if index in slip else "secondary",
                          use_container_width=True, on_click=_toggle, args=(index, candidates))


def _game_filter(candidates: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Chips to look at one game, or all of them. Returns the legs to show (they keep their
    positions in the full table, which is what the slip refers to) and whether one game is
    chosen. The choice applies to the suggested slips and the prop list alike."""
    matchups = candidates.drop_duplicates("Game").set_index("Game")
    short = {game: f"{row.away_abbr} @ {row.home_abbr}" for game, row in matchups.iterrows()}
    picked = style.choose("Game", [ALL_GAMES, *short], "browse_game",
                          format_func=lambda g: g if g == ALL_GAMES else short[g])
    if picked == ALL_GAMES:
        return candidates, False
    return candidates[candidates["Game"] == picked], True


@st.cache_data(show_spinner=False, max_entries=64)
def _slips(pool: pd.DataFrame, style_name: str, one_per_game: bool) -> pd.DataFrame:
    """The suggested slips for these legs and this style. Remembered, because every tap on a
    price reruns the screen and the same legs would otherwise be searched all over again."""
    return nba_parlay.suggest_parlays(pool, top=IDEAS_SHOWN,
                                      min_chance=nba_parlay.STYLES[style_name],
                                      min_profit=nba_parlay.MIN_PROFIT[style_name],
                                      real_leg_decimal=nba_parlay.REAL_LEG_DECIMAL,
                                      one_per_game=one_per_game)


def _suggested(candidates: pd.DataFrame, shown: pd.DataFrame | None = None,
               single_game: bool = False) -> None:
    st.markdown("#### Ideas the model likes")
    style_name = style.choose("How much risk?", list(nba_parlay.STYLES), "slip_style",
                              default=nba_parlay.DEFAULT_STYLE)
    pool = candidates if shown is None else shown
    slips = _slips(pool, style_name, not single_game)
    if single_game:
        st.caption("One game: these bets move together, and the chance accounts for that.")
    if slips.empty:
        st.info("Nothing fits that style here. It takes bets worth making on their own "
                + ("from different players in this game" if single_game
                   else "in at least two different games")
                + ", and a real chance of the whole slip hitting. Try a bigger-payout style.")
        return
    for position, idea in enumerate(slips.itertuples()):
        legs = [(nba_parlay.headshot_url(row.player_id), row.Player,
                 _with_average(row.Leg.split(" · ")[-1] if " · " in row.Leg else row.Leg,
                               row.player_id, row.stat_key), str(row.Odds))
                for row in candidates.loc[idea.bets].itertuples()]
        st.markdown(style.idea_card(legs, f"{idea._3:.0f}%", f"${idea.Pays + 1:,.2f}"),
                    unsafe_allow_html=True)
        st.button("Add to slip", key=f"idea_{position}", on_click=_load, args=(idea.bets,),
                  use_container_width=True)


def _with_average(bet: str, player_id, stat: str = "points") -> str:
    """The bet with the player's average beside it, so a line can be judged at a glance."""
    average = nba_parlay.average_text(averages_by_player(), player_id,
                                      nba_parlay.stat_column(stat))
    return f"{bet} · {average}" if average else bet


def _browse(shown: pd.DataFrame, candidates: pd.DataFrame, book: str = nba_parlay.BOOK) -> None:
    """Every prop in `shown`, a section per stat. `candidates` is the full table the slip
    indexes into; `shown` may be one game's worth of it."""
    st.markdown("#### All props")
    matchups = shown.drop_duplicates("Game").set_index("Game")
    short = {game: f"{row.away_abbr} @ {row.home_abbr}" for game, row in matchups.iterrows()}
    slip = set(st.session_state.get(LEGS_KEY, []))
    view = style.choose("View", ["List", "Grid"], f"browse_view_{book}",
                        default="List" if book == "kalshi" else "Grid")
    if view == "List":
        st.caption("Pick how many, then tap Yes or No to add it. Tap it again to remove it.")
    else:
        st.caption("Tap a price to add it, tap it again to remove it. **O** is over, **U** is "
                   "under, **More** has the other lines.")
    row_view = _ladder_row if view == "List" else _player_row
    stats = [s for s in nba_stat_model.STATS if s in set(shown["stat_key"])]
    for position, stat in enumerate(stats):
        label = f"Player {nba_stat_model.STATS[stat].label}"
        with st.expander(label, expanded=position == 0), st.container(key=f"browse-list-{stat}"):
            of_stat = shown[shown["stat_key"] == stat]
            for game in short:
                day = of_stat[of_stat["Game"] == game]
                if day.empty:
                    continue
                st.markdown(f"##### {short[game]}")
                stars_first = day.groupby("player_id")["line"].max().sort_values(
                    ascending=False).index
                for player_id in stars_first:
                    row_view(day[day["player_id"] == player_id], slip, candidates, book)


def _player_row(rows: pd.DataFrame, slip: set, candidates: pd.DataFrame,
                book: str = nba_parlay.BOOK) -> None:
    photo, name, over, under, more = st.columns([1, 3, 2, 2, 2], vertical_alignment="center")
    first = rows.iloc[0]
    photo.image(nba_parlay.headshot_url(first["player_id"]), width=44)
    name.markdown(f"**{first['Player']}**{injury_badge(first['Player'])}")
    column = nba_parlay.stat_column(first["stat_key"])
    if text := nba_parlay.average_text(averages_by_player(), first["player_id"], column):
        name.caption(text)
    main_rows = rows[rows["Side"].isin(["Over", "Under"])]
    featured = nba_parlay.main_line(main_rows)
    shown = main_rows[main_rows["line"] == featured]
    for target, side in ((over, "Over"), (under, "Under")):
        match = shown[shown["Side"] == side]
        if not match.empty:
            _price_button(target, match.index[0], match.iloc[0], slip, candidates,
                          f"{side[0]} {match.iloc[0]['line']:g}")
    others = main_rows[main_rows["line"] != featured].sort_values(
        ["line", "Side"], ascending=[True, False])
    totals = rows[~rows["Side"].isin(["Over", "Under"])].sort_values("line")
    if others.empty and totals.empty:
        return
    on_slip = any(index in slip for index in [*others.index, *totals.index])
    with more.popover("✓ More" if on_slip else "More", use_container_width=True):
        for line in others["line"].unique():
            left, right = st.columns(2)
            for target, side in ((left, "Over"), (right, "Under")):
                match = others[(others["line"] == line) & (others["Side"] == side)]
                if not match.empty:
                    _price_button(target, match.index[0], match.iloc[0], slip, candidates,
                                  f"{side[0]} {line:g}")
        for index, row in totals.iterrows():
            _price_button(st, index, row, slip, candidates, f"{int(row['line'] + 0.5)}+")


def _ladder_row(rows: pd.DataFrame, slip: set, candidates: pd.DataFrame,
                book: str = nba_parlay.BOOK) -> None:
    """One player as a Kalshi-style row: his name and the market's chance for the step you
    picked, a stepper of "at least this many" choices, and Yes / No prices."""
    steps = nba_parlay.ladder(rows)
    if not steps:
        return
    first = rows.iloc[0]
    column = nba_parlay.stat_column(first["stat_key"])
    start = nba_parlay.default_step(steps)["threshold"]
    key = f"step_{first['stat_key']}_{book}_{first['player_id']}"
    photo, name, chance = st.columns([1, 4, 2], vertical_alignment="center")
    photo.image(nba_parlay.headshot_url(first["player_id"]), width=44)
    pick, yes, no = st.columns([5, 2, 2], vertical_alignment="center")
    options = [s["threshold"] for s in steps]
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)
    chosen = pick.pills("At least", options, selection_mode="single", default=start, key=key,
                        format_func=lambda t: f"{t}+", label_visibility="collapsed")
    step = next(s for s in steps if s["threshold"] == (chosen if chosen is not None else start))
    name.markdown(f"**{first['Player']}** · {step['threshold']}+{injury_badge(first['Player'])}")
    if text := nba_parlay.average_text(averages_by_player(), first["player_id"], column):
        name.caption(text)
    chance.markdown(f"<div class='bk-chance'>{step['market']:.0f}%"
                    f"<span>model {step['model']:.0f}%</span></div>", unsafe_allow_html=True)
    _side_button(yes, step["yes"], "Yes", candidates, slip, book)
    if step["no"] is not None:
        _side_button(no, step["no"], "No", candidates, slip, book)


def _side_button(container, index: int, side: str, candidates: pd.DataFrame, slip: set,
                 book: str) -> None:
    """Yes / No with the price: cents on Kalshi, American odds elsewhere."""
    odds = candidates.loc[index, "Odds"]
    price = f"{nba_parlay.cents(odds)}¢" if book == "kalshi" else shared.fmt_american(odds)
    chosen = index in slip
    container.button(
        f"{'✓ ' if chosen else ''}{side} {price}", key=f"add_{index}",
        type="primary" if chosen else "secondary", use_container_width=True,
        on_click=_toggle, args=(index, candidates))


def _price_button(container, index: int, row: pd.Series, slip: set, candidates: pd.DataFrame,
                  label: str) -> None:
    chosen = index in slip
    container.button(
        f"{'✓ ' if chosen else ''}{label}  {shared.fmt_american(row['Odds'])}",
        key=f"add_{index}", type="primary" if chosen else "secondary",
        use_container_width=True, on_click=_toggle, args=(index, candidates))


def _search(candidates: pd.DataFrame) -> None:
    with st.expander("Search for a specific bet"):
        st.multiselect(
            "Type a player's name", list(candidates.index), key=LEGS_KEY,
            format_func=lambda i: _describe(candidates.loc[i]),
            help="One bet per player per stat. This is the same slip as the one on the right.")


# ---- the slip panel ---------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def injuries_by_name() -> dict[str, nba_injuries.Injury]:
    """Today's injury report by normalised name; empty if it can't be fetched,
    so a problem there never gets in the way of building a slip."""
    try:
        return nba_injuries.status_by_name(nba_injuries.fetch_injuries())
    except nba_injuries.InjuryDataError:
        return {}


def injury_badge(player: str) -> str:
    """Markdown for a small coloured badge if the player is on the report, else ''."""
    injury = injuries_by_name().get(nba_players.normalize_name(player))
    if injury is None:
        return ""
    badge = nba_injuries.label(injury)
    return f" :red[**{badge}**]" if injury.is_out else f" :orange[{badge}]"


@st.cache_data(ttl=3600, show_spinner=False)
def teams_by_player() -> dict[int, str]:
    """Each player's team from the cached game logs; empty if unavailable."""
    today = dt.date.today()
    try:
        return nba_parlay.player_teams(
            nba_stats.load_season(nba_stats.current_season(today), today=today))
    except nba_stats.NbaDataError:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def averages_by_player() -> dict:
    """Season and last-10 averages from the cached game logs; empty if unavailable."""
    today = dt.date.today()
    try:
        # two seasons, so "last 10" still means ten games early in a new season
        games = pd.concat([nba_stats.load_season(season, today=today)
                           for season in nba_stats.recent_seasons(today, 2)], ignore_index=True)
        return nba_parlay.player_averages(games)
    except nba_stats.NbaDataError:
        return {}


def _slip_panel(candidates: pd.DataFrame, current) -> None:
    if current is None:
        st.markdown("#### Your slip")
        st.markdown(
            style.empty_slip("Your slip is empty", "Tap a price to add a bet."),
            unsafe_allow_html=True)
        return
    chosen, summary = current
    kind = "single bet" if len(chosen) == 1 else f"{len(chosen)}-leg parlay"
    st.markdown(f"#### Your slip · {kind}")
    teams = teams_by_player()
    for index, bet in chosen.iterrows():
        team = teams.get(int(bet["player_id"]), "")
        card, remove = st.columns([10, 2], vertical_alignment="center")
        card.markdown(
            style.leg_card(nba_parlay.headshot_url(bet["player_id"]), bet["Player"],
                           bet["Leg"].split(" · ", 1)[1], shared.fmt_american(bet["Odds"]),
                           compact=True, accent=team_colors.team_color(team) if team else "",
                           logo=nba_live.logo_url(team) if team else ""),
            unsafe_allow_html=True)
        remove.button("✕", key=f"rm_{index}", on_click=_toggle, args=(index, candidates),
                      help=f"Remove {bet['Player']}", use_container_width=True)
    _injury_warning(chosen)
    stake = _stake_input()
    _slip_box(summary, chosen, stake)
    st.markdown(f"**{nba_parlay.verdict(summary['ev_per_unit'])}**")
    st.button("Clear slip", key="clear_slip", on_click=_clear_slip, use_container_width=True)
    with st.expander("See the odds in detail"):
        _result(summary, chosen)
        _chance_chart(chosen, summary)
        _leg_table(chosen)
        st.caption(_correlation_note(summary))


def _injury_warning(chosen: pd.DataFrame) -> None:
    """Say so plainly if anyone on the slip is listed out or doubtful."""
    report = injuries_by_name()
    out = [name for name in chosen["Player"]
           if (injury := report.get(nba_players.normalize_name(name))) and injury.is_out]
    if out:
        st.warning(f"{', '.join(out)} {'is' if len(out) == 1 else 'are'} listed out on the "
                   "injury report. A bet on a player who doesn't play is usually voided, but "
                   "check your book's rules before betting.")


def _stake_input() -> float:
    return st.number_input(
        "How much are you betting? ($)", min_value=0.0, value=DEFAULT_STAKE, step=5.0,
        format="%.2f", key="stake",
        help="Only used to show dollars. Nothing is placed, and nothing is saved.")


def _slip_box(summary: dict, chosen: pd.DataFrame, stake: float) -> None:
    result = nba_parlay.stake_outcomes(stake, summary["decimal_odds"], summary["ev_per_unit"])
    p = summary["joint_probability"]
    st.markdown(style.slip_summary(
        "PARLAY" if len(chosen) > 1 else "SINGLE BET",
        f"To win {nba_parlay.money(result['profit_if_wins'])}",
        [("Stake", nba_parlay.money(stake)),
         ("Total return", nba_parlay.money(result["total_return"])),
         ("Chance it hits", f"{p * 100:.1f}%  ({nba_parlay.one_in(p)})"),
         ("Average result at this stake",
          nba_parlay.money(result["expected_profit"], signed=True))]),
        unsafe_allow_html=True)


def _result(summary: dict, chosen: pd.DataFrame) -> None:
    p = summary["joint_probability"]
    payout = (correlated.decimal_to_american(summary["decimal_odds"])
              if len(chosen) > 1 else chosen["Odds"].iloc[0])
    top = st.columns(2)
    top[0].metric("Chance every bet hits", f"{p * 100:.1f}%")
    top[1].metric("Odds that break even", shared.fmt_american(summary["fair_american"]))
    bottom = st.columns(2)
    bottom[0].metric("Payout if the odds multiply", shared.fmt_american(payout))
    bottom[1].metric("Expected profit per $1", f"{summary['ev_per_unit']:+.2f}")


def _chance_chart(chosen: pd.DataFrame, summary: dict) -> None:
    """Each bet's chance, then the chance they all hit: shows how fast a parlay shrinks."""
    bars = pd.DataFrame({
        "Bet": list(chosen["Leg"]) + ["ALL BETS HIT"],
        "Chance %": list(chosen["Blended %"]) + [summary["joint_probability"] * 100.0],
        "Kind": ["One bet"] * len(chosen) + ["The parlay"],
    })
    chart = alt.Chart(bars).mark_bar().encode(
        x=alt.X("Chance %:Q", scale=alt.Scale(domain=[0, 100]), title="Chance it hits (%)"),
        y=alt.Y("Bet:N", sort=None, title=None,
                axis=alt.Axis(labelLimit=420, labelOverlap=False)),
        color=alt.Color("Kind:N", legend=None,
                        scale=alt.Scale(domain=["One bet", "The parlay"],
                                        range=["#5b8def", "#f2994a"])),
        tooltip=["Bet", alt.Tooltip("Chance %:Q", format=".1f")],
    ).properties(height=max(150, 44 * len(bars)))
    st.altair_chart(chart, use_container_width=True)


def _leg_table(chosen: pd.DataFrame) -> None:
    table = chosen.assign(
        Photo=[nba_parlay.headshot_url(pid) for pid in chosen["player_id"]],
        Odds=chosen["Odds"].map(shared.fmt_american),
    )[["Photo", "Leg", "Game", "Odds", "Model %", "Market %", "Blended %", "Leg EV %"]]
    st.dataframe(
        table.rename(columns={
            "Model %": "Model chance %", "Market %": "FanDuel's chance %",
            "Blended %": "Used here %", "Leg EV %": "Profit per $1 (%)"}),
        use_container_width=True, hide_index=True, row_height=48, column_config={
            "Photo": st.column_config.ImageColumn(" ", width="small"),
            "Model chance %": st.column_config.NumberColumn(format="%.1f"),
            "FanDuel's chance %": st.column_config.NumberColumn(format="%.1f"),
            "Used here %": st.column_config.NumberColumn(
                format="%.1f", help="The model's chance blended 30/70 toward FanDuel's, "
                                    "since the raw model is overconfident."),
            "Profit per $1 (%)": st.column_config.NumberColumn(format="%+.1f"),
        })


def _describe(row: pd.Series) -> str:
    return f"{row['Leg']}  ({shared.fmt_american(row['Odds'])})  ·  {row['Game']}"


def _correlation_note(summary: dict) -> str:
    gap = (summary["joint_probability"] - summary["independent_probability"]) * 100
    return (
        f"Multiplying the bets as if they were unrelated gives "
        f"{summary['independent_probability'] * 100:.1f}%; allowing for bets from the "
        f"same game moves it {gap:+.1f} points. Over three seasons, teammates' points "
        "moved very slightly against each other and opponents' very slightly together, "
        "so for points alone it barely matters. It would matter a lot for bets tied to "
        "the same game's total or result, which this doesn't cover. The payout shown is "
        "each bet's price multiplied; FanDuel prices same-game parlays itself and "
        "usually pays less, so check its quote before betting."
    )
