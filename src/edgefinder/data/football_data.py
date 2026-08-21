"""Free historical soccer results from football-data.co.uk.

CSV per league per season (columns HomeTeam, AwayTeam, FTHG, FTAG).
Team names differ from The Odds API's ("Man United" vs "Manchester
United"), so an alias map plus fuzzy matching bridges the two.
"""

import csv
import difflib
import io

import requests

from . import cache

BASE = "https://www.football-data.co.uk/mmz4281"
DIVISIONS = {
    "EPL": "E0", "La Liga": "SP1", "Bundesliga": "D1",
    "Serie A": "I1", "Ligue 1": "F1",
}
CACHE_SECONDS = 24 * 3600
REQUEST_TIMEOUT = 30

# odds-api name -> football-data name, for the ones fuzzy match misses
ALIASES = {
    "Manchester United": "Man United",
    "Manchester City": "Man City",
    "Wolverhampton Wanderers": "Wolves",
    "Brighton and Hove Albion": "Brighton",
    "West Ham United": "West Ham",
    "Newcastle United": "Newcastle",
    "Tottenham Hotspur": "Tottenham",
    "Nottingham Forest": "Nott'm Forest",
    "Leeds United": "Leeds",
    "Atletico Madrid": "Ath Madrid",
    "Athletic Bilbao": "Ath Bilbao",
    "Real Betis": "Betis",
    "Real Sociedad": "Sociedad",
    "Rayo Vallecano": "Vallecano",
    "Espanyol": "Espanol",
    "Celta Vigo": "Celta",
    "Borussia Dortmund": "Dortmund",
    "Borussia Monchengladbach": "M'gladbach",
    "Bayer Leverkusen": "Leverkusen",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "FSV Mainz 05": "Mainz",
    "TSG Hoffenheim": "Hoffenheim",
    "VfB Stuttgart": "Stuttgart",
    "VfL Wolfsburg": "Wolfsburg",
    "FC Augsburg": "Augsburg",
    "SC Freiburg": "Freiburg",
    "Werder Bremen": "Werder Bremen",
    "1. FC Union Berlin": "Union Berlin",
    "Inter Milan": "Inter",
    "AC Milan": "Milan",
    "AS Roma": "Roma",
    "Hellas Verona": "Verona",
    "Paris Saint Germain": "Paris SG",
    "Saint Etienne": "St Etienne",
}


class FootballDataError(Exception):
    pass


def season_codes(year: int, month: int) -> list[str]:
    """Seasons to train on: the last completed one plus the current one
    (European seasons run Aug-May)."""
    if month >= 8:
        current_start = year
    else:
        current_start = year - 1
    def code(start: int) -> str:
        return f"{start % 100:02d}{(start + 1) % 100:02d}"
    return [code(current_start - 1), code(current_start)]


def league_results(league: str, season_code: str) -> list[dict]:
    """[{home, away, home_goals, away_goals}] for one league season.
    Returns [] when the season file doesn't exist yet."""
    division = DIVISIONS[league]
    url = f"{BASE}/{season_code}/{division}.csv"
    cache_key = f"footballdata_{division}_{season_code}"
    cached = cache.get(cache_key, CACHE_SECONDS)
    if cached is not None:
        return cached
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        stale = cache.get(cache_key, float("inf"))
        return stale if stale is not None else []
    matches = _parse_csv(response.text)
    cache.put(cache_key, matches)
    return matches


def _parse_csv(text: str) -> list[dict]:
    matches = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        home, away = row.get("HomeTeam"), row.get("AwayTeam")
        fthg, ftag = row.get("FTHG"), row.get("FTAG")
        if not home or not away or not fthg or not ftag:
            continue
        try:
            matches.append({
                "home": home, "away": away,
                "home_goals": int(fthg), "away_goals": int(ftag),
            })
        except ValueError:
            continue
    return matches


def map_team_name(odds_api_name: str, known_names: set[str]) -> str | None:
    """Translate an Odds API team name to the football-data name."""
    if odds_api_name in known_names:
        return odds_api_name
    alias = ALIASES.get(odds_api_name)
    if alias in known_names:
        return alias
    close = difflib.get_close_matches(odds_api_name, list(known_names),
                                      n=1, cutoff=0.75)
    return close[0] if close else None
