"""Client for the free MLB Stats API (statsapi.mlb.com, no key needed).

Every call is cached to disk; the season results cache is refreshed a
few times a day, today's schedule more often.
"""

import requests

from . import cache

BASE = "https://statsapi.mlb.com/api/v1"
SEASON_CACHE_SECONDS = 6 * 3600
SCHEDULE_CACHE_SECONDS = 30 * 60
STATS_CACHE_SECONDS = 12 * 3600
REQUEST_TIMEOUT = 20


class MlbApiError(Exception):
    pass


def _get_json(url: str, cache_key: str, max_age: float) -> dict:
    cached = cache.get(cache_key, max_age)
    if cached is not None:
        return cached
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        stale = cache.get(cache_key, float("inf"))
        if stale is not None:
            return stale
        raise MlbApiError(f"MLB Stats API request failed: {exc}") from exc
    payload = response.json()
    cache.put(cache_key, payload)
    return payload


def season_results(season: int) -> list[dict]:
    """All completed regular-season games: home/away names and scores."""
    url = f"{BASE}/schedule?sportId=1&season={season}&gameType=R"
    payload = _get_json(url, f"mlb_season_{season}", SEASON_CACHE_SECONDS)
    games = []
    for date_entry in payload.get("dates", []):
        for game in date_entry.get("games", []):
            status = game.get("status", {}).get("abstractGameState")
            home = game.get("teams", {}).get("home", {})
            away = game.get("teams", {}).get("away", {})
            if status != "Final":
                continue
            if "score" not in home or "score" not in away:
                continue
            games.append({
                "date": date_entry.get("date"),
                "home": home["team"]["name"],
                "away": away["team"]["name"],
                "home_id": home["team"]["id"],
                "away_id": away["team"]["id"],
                "home_score": home["score"],
                "away_score": away["score"],
            })
    return games


def todays_schedule(date_iso: str) -> list[dict]:
    """Games on a date with probable pitchers where announced."""
    url = (
        f"{BASE}/schedule?sportId=1&date={date_iso}"
        "&hydrate=probablePitcher,team"
    )
    payload = _get_json(url, f"mlb_sched_{date_iso}", SCHEDULE_CACHE_SECONDS)
    games = []
    for date_entry in payload.get("dates", []):
        for game in date_entry.get("games", []):
            home = game.get("teams", {}).get("home", {})
            away = game.get("teams", {}).get("away", {})
            games.append({
                "game_time": game.get("gameDate"),
                "status": game.get("status", {}).get("abstractGameState"),
                "home": home.get("team", {}).get("name"),
                "away": away.get("team", {}).get("name"),
                "home_id": home.get("team", {}).get("id"),
                "away_id": away.get("team", {}).get("id"),
                "home_pitcher": _pitcher_summary(home.get("probablePitcher")),
                "away_pitcher": _pitcher_summary(away.get("probablePitcher")),
            })
    return games


def _pitcher_summary(pitcher: dict | None) -> dict | None:
    if not pitcher:
        return None
    return {"id": pitcher.get("id"), "name": pitcher.get("fullName")}


def pitcher_season_era(person_id: int, season: int) -> float | None:
    url = (
        f"{BASE}/people/{person_id}/stats"
        f"?stats=season&group=pitching&season={season}"
    )
    payload = _get_json(url, f"mlb_era_{person_id}_{season}", STATS_CACHE_SECONDS)
    for stat_group in payload.get("stats", []):
        for split in stat_group.get("splits", []):
            era = split.get("stat", {}).get("era")
            if era is not None:
                try:
                    return float(era)
                except ValueError:
                    return None
    return None


def pitcher_strikeouts_by_start(person_id: int, season: int) -> list[int]:
    """Ks in each appearance, newest first."""
    url = (
        f"{BASE}/people/{person_id}/stats"
        f"?stats=gameLog&group=pitching&season={season}"
    )
    payload = _get_json(url, f"mlb_klog_{person_id}_{season}", STATS_CACHE_SECONDS)
    strikeouts = []
    for stat_group in payload.get("stats", []):
        for split in stat_group.get("splits", []):
            k = split.get("stat", {}).get("strikeOuts")
            if k is not None:
                strikeouts.append(int(k))
    strikeouts.reverse()
    return strikeouts


def team_hitting_k_per_game(season: int) -> dict[str, float]:
    """Team name -> strikeouts per game at the plate (for prop model)."""
    url = (
        f"{BASE}/teams/stats?sportId=1&group=hitting"
        f"&stats=season&season={season}"
    )
    try:
        payload = _get_json(url, f"mlb_team_k_{season}", STATS_CACHE_SECONDS)
    except MlbApiError:
        return {}
    rates = {}
    for stat_group in payload.get("stats", []):
        for split in stat_group.get("splits", []):
            team = split.get("team", {}).get("name")
            stat = split.get("stat", {})
            strikeouts = stat.get("strikeOuts")
            games = stat.get("gamesPlayed")
            if team and strikeouts and games:
                rates[team] = strikeouts / games
    return rates
