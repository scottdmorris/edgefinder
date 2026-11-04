"""Matching player and team names between The Odds API and NBA stats.

The two feeds spell names differently (accents, "Jr.", "P.J." vs "PJ"),
so everything is compared in a normalized form, and a player is only
matched against the two teams actually playing in that game.
"""

import functools
import re
import unicodedata

import pandas as pd

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    unaccented = "".join(c for c in decomposed if not unicodedata.combining(c))
    spaced = unaccented.lower().replace("-", " ")
    tokens = re.sub(r"[^a-z0-9 ]", "", spaced).split()
    while len(tokens) > 1 and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


@functools.lru_cache(maxsize=1)
def _teams() -> list[dict]:
    from nba_api.stats.static import teams  # bundled data, no network

    return teams.get_teams()


def team_abbreviation(team_name: str) -> str | None:
    """'Los Angeles Clippers' -> 'LAC'. Matches on the nickname, since
    the Odds API says 'Los Angeles' where the NBA says 'LA'."""
    words = team_name.split()
    for team in _teams():
        nickname = team["nickname"].split()
        if words[-len(nickname):] == nickname:
            return team["abbreviation"]
    return None


def match_players(names: list[str], games: pd.DataFrame, team_abbrs: set[str]) -> dict[str, int]:
    """Map odds-feed player names to NBA player ids, among players whose
    most recent game was for one of `team_abbrs` (so trades are handled)."""
    latest = games.sort_values("game_date").groupby("player_id").tail(1)
    on_teams = latest[latest["team"].isin(team_abbrs)]
    by_name = {normalize_name(row.player_name): int(row.player_id)
               for row in on_teams.itertuples()}
    matched = {}
    for name in names:
        player_id = by_name.get(normalize_name(name))
        if player_id is not None:
            matched[name] = player_id
    return matched
