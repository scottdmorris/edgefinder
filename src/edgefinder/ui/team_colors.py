"""Team colors for the app's dark background.

These are display colors, not official brand values. Several teams' real
primaries are so dark (navy, black) that they would disappear on this
background, so those use their lighter accent instead.
"""

DEFAULT = "#EFF3F4"
WHITE = "#F4F7FB"
_CLASH_DISTANCE = 90.0      # colors closer than this (in RGB) read as the same team

COLORS = {
    "ATL": "#E03A3E", "BOS": "#00A651", "BKN": "#C4CED4", "CHA": "#00A3C4",
    "CHI": "#CE1141", "CLE": "#B01E4D", "DAL": "#0077C8", "DEN": "#FEC524",
    "DET": "#E21F3F", "GSW": "#FFC72C", "HOU": "#D5123F", "IND": "#FDBB30",
    "LAC": "#C8102E", "LAL": "#FDB927", "MEM": "#7E97CC", "MIA": "#E8503A",
    "MIL": "#2E9E5B", "MIN": "#78BE20", "NOP": "#D3A04B", "NYK": "#F58426",
    "OKC": "#1A9AE0", "ORL": "#1A8FE0", "PHI": "#2A8BDB", "PHX": "#E56020",
    "POR": "#E03A3E", "SAC": "#7B4DB5", "SAS": "#C4CED4", "TOR": "#E0203F",
    "UTA": "#F9A01B", "WAS": "#E31837",
}


def team_color(code: str) -> str:
    """The team's display color, or the app's blue for an unknown code."""
    return COLORS.get(code, DEFAULT)


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _distance(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5


def matchup_colors(away: str, home: str) -> tuple[str, str]:
    """Colors for the two teams in a game, kept apart: two similar teams
    (two reds, two greens) would be unreadable on a shot chart, so the home
    team falls back to white when they clash."""
    away_color, home_color = team_color(away), team_color(home)
    if _distance(away_color, home_color) < _CLASH_DISTANCE:
        home_color = WHITE
    return away_color, home_color


def rgba(color: str, alpha: float) -> str:
    """'#1493FF' at 0.15 -> 'rgba(20,147,255,0.15)', for tinted backgrounds."""
    red, green, blue = _rgb(color)
    return f"rgba({red},{green},{blue},{alpha})"
