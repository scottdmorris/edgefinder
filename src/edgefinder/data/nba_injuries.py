"""Who is injured tonight, from ESPN's free injury feed.

This is an unofficial, undocumented feed, fine for a personal tool but not a
licensed source, so a failure here must never stop anything else: every fetch
turns trouble into one InjuryDataError, and callers carry on with "nobody
known to be out".

Statuses seen in the feed: Out, Day-To-Day, and occasionally Questionable,
Doubtful or Probable. Only Out and Doubtful are treated as not playing.
"""

from dataclasses import dataclass

import requests

from . import nba_players

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
REQUEST_TIMEOUT = 15
OUT_STATUSES = {"out", "doubtful"}


class InjuryDataError(Exception):
    pass


@dataclass(frozen=True)
class Injury:
    name: str
    team: str          # tricode, e.g. "NYK"; empty if the team name isn't recognised
    status: str        # as the feed words it: "Out", "Day-To-Day", ...
    detail: str        # the short comment, may be empty

    @property
    def is_out(self) -> bool:
        return self.status.lower() in OUT_STATUSES


def parse_injuries(payload: dict) -> list[Injury]:
    """Every listed injury. Entries without a player name are skipped."""
    injuries = []
    for team in payload.get("injuries", []):
        code = nba_players.team_abbreviation(team.get("displayName", "")) or ""
        for entry in team.get("injuries", []):
            name = (entry.get("athlete") or {}).get("displayName")
            if not name:
                continue
            injuries.append(Injury(
                name=name, team=code, status=(entry.get("status") or "").strip(),
                detail=(entry.get("shortComment") or "").strip()))
    return injuries


def fetch_injuries() -> list[Injury]:
    try:
        response = requests.get(URL, timeout=REQUEST_TIMEOUT,
                                headers={"User-Agent": "ball-knowledge"})
        response.raise_for_status()
        return parse_injuries(response.json())
    except Exception as exc:
        raise InjuryDataError(f"The injury report is unavailable ({type(exc).__name__})") from None


def label(injury: Injury) -> str:
    """A short badge: 'OUT' for anyone ruled out, otherwise the feed's own word
    ('DAY-TO-DAY', 'QUESTIONABLE')."""
    return "OUT" if injury.is_out else injury.status.upper()


def status_by_name(injuries: list[Injury]) -> dict[str, Injury]:
    """Each listed player by his normalised name, for looking up one player."""
    return {nba_players.normalize_name(i.name): i for i in injuries}


def out_player_ids(injuries: list[Injury], games, season: str) -> set[int]:
    """The NBA ids of players ruled out, matched through the season's box
    scores. A listed player who can't be matched to a team's roster is
    left out of the answer, not guessed."""
    this_season = games[games["season"] == season]
    ids: set[int] = set()
    by_team: dict[str, list[str]] = {}
    for injury in injuries:
        if injury.is_out and injury.team:
            by_team.setdefault(injury.team, []).append(injury.name)
    for team, names in by_team.items():
        ids.update(nba_players.match_players(names, this_season, {team}).values())
    return ids
