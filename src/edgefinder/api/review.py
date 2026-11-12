"""The Last night screen's data: how a graded game day went, pick by pick and model by model,
and how a saved slip did against the box scores. Read-only, from the ledger and the game logs.
"""

import pandas as pd

from ..models import nba_stat_model
from ..tracking import nba_paper, nba_parlay, nba_view
from . import service

MISSES_SHOWN = 5
LOW_MINUTES_SHARE = 0.6        # under this share of his usual minutes, a quiet night has a reason
USUAL_GAMES = 10
HIT, MISSED, VOID, PENDING = "Hit", "Missed", "Didn't play", "Not graded yet"


def _picks(ledger: pd.DataFrame) -> pd.DataFrame:
    return ledger[ledger["pick_side"].notna()]


def graded_dates(ledger: pd.DataFrame) -> list[str]:
    """Game days with at least one graded pick, newest first."""
    picks = _picks(ledger)
    return sorted(picks.loc[picks["status"] == "settled", "game_date"].unique(), reverse=True)


def _minutes(games: pd.DataFrame, date: str) -> tuple[dict[int, float], dict[int, float]]:
    """Each player's minutes on `date`, and his average over the games before it."""
    if games.empty:
        return {}, {}
    day = pd.Timestamp(date)
    played = games[games["game_date"] == day]
    before = games[games["game_date"] < day].sort_values("game_date")
    usual = before.groupby("player_id")["minutes"].apply(lambda m: float(m.tail(USUAL_GAMES).mean()))
    return dict(zip(played["player_id"].astype(int), played["minutes"].astype(float))), usual.to_dict()


def _minutes_note(player_id: int, played: dict, usual: dict, logs_in: bool) -> str:
    """Why a night may have gone wrong that the model could not have known."""
    if not logs_in:
        return ""
    if player_id not in played:
        return "Did not play"
    normal = usual.get(player_id)
    if normal and played[player_id] < LOW_MINUTES_SHARE * normal:
        return f"Played {played[player_id]:.0f} minutes, usually {normal:.0f}"
    return ""


def _pick_rows(day: pd.DataFrame, played: dict, usual: dict, logs_in: bool) -> list[dict]:
    """One row per bet; several models liking the same bet share a row."""
    rows = []
    for (player_id, line, side), group in day.groupby(["player_id", "line", "pick_side"], sort=False):
        first = group.iloc[0]
        settled = group[group["status"] == "settled"]
        result = settled.iloc[0]["result"] if not settled.empty else None
        status = {"win": HIT, "loss": MISSED}.get(result, VOID if (group["status"] == "void").all()
                                                  else PENDING)
        actual = settled.iloc[0]["actual"] if not settled.empty else None
        projects = float(group["model_mean"].astype(float).mean())
        rows.append({
            "player": first["player"], "player_id": int(player_id),
            "photo": nba_parlay.headshot_url(player_id),
            "bet": f"{str(side).capitalize()} {float(line)} points",
            "game_short": nba_view.short_game(f"{first['away']} @ {first['home']}"),
            "odds": None if pd.isna(first["pick_odds"]) else int(first["pick_odds"]),
            "models": [service.model_short(v) for v in group["model_version"]],
            "projects": service._num(projects, 1), "actual": service._num(actual, 0),
            "status": status,
            "off_by": None if actual is None or pd.isna(actual)
            else service._num(abs(float(actual) - projects), 1),
            "note": _minutes_note(int(player_id), played, usual, logs_in) if status == MISSED else "",
        })
    order = {MISSED: 0, HIT: 1, PENDING: 2, VOID: 3}
    return sorted(rows, key=lambda r: (order[r["status"]], -(r["off_by"] or 0)))


def _models(day: pd.DataFrame) -> list[dict]:
    out = []
    for version in sorted(day["model_version"].dropna().unique(), reverse=True):
        night = nba_paper.summary(day, model_version=version)
        if night["picks"]:
            out.append({"id": version, "short": service.model_short(version),
                        "record": night["record"], "picks": night["picks"],
                        "settled": night["settled"], "units": service._num(night["units"])})
    return sorted(out, key=lambda m: -(m["units"] or 0))


def review(date: str | None = None) -> dict:
    """A graded game day: each model's night, every pick, and the misses worth a second look."""
    def build() -> dict:
        ledger = service.load_ledger()
        dates = graded_dates(ledger)
        if not dates:
            raise service.NotFound("no graded picks yet")
        chosen = date or dates[0]
        if chosen not in dates:
            raise service.NotFound(f"no graded picks on {chosen}")
        night = ledger[ledger["game_date"] == chosen]
        fanduel = _picks(nba_paper.scope(night, book=nba_paper.DEFAULT_BOOK))
        games = service.load_games()
        played, usual = _minutes(games, chosen)
        logs_in = bool(played)
        picks = _pick_rows(fanduel, played, usual, logs_in)
        kalshi = nba_paper.summary(night, book="kalshi")
        return {
            "date": chosen, "label": nba_view.day_label(chosen, service.today()),
            "days": [{"date": d, "label": nba_view.day_label(d, service.today())} for d in dates],
            "models": _models(fanduel), "picks": picks,
            "misses": [p for p in picks if p["status"] == MISSED][:MISSES_SHOWN],
            "pending": sum(p["status"] == PENDING for p in picks),
            "kalshi": {"record": kalshi["record"], "settled": kalshi["settled"],
                       "units": service._num(kalshi["units"])} if kalshi["settled"] else None,
        }
    return service.cached(("review", date), build, 120)


def grade_slip(date: str, legs: list[dict]) -> dict:
    """How a saved slip did against the box scores: each leg, and the leg that sank it."""
    games = service.load_games()
    day = games[games["game_date"] == pd.Timestamp(date)] if not games.empty else games
    logs_in = not day.empty
    played, usual = _minutes(games, date)
    by_player = {int(r["player_id"]): r for r in day.to_dict("records")} if logs_in else {}
    graded = []
    for leg in legs:
        stat = nba_stat_model.STATS.get(leg["stat"])
        if stat is None:
            raise ValueError(f"unknown stat {leg['stat']}")
        row = by_player.get(int(leg["player_id"]))
        actual = None if row is None else int(row[stat.column])
        over = leg["side"] != "Under"
        if not logs_in:
            status = PENDING
        elif row is None:
            status = VOID
        else:
            status = HIT if (actual > leg["line"]) == over else MISSED
        graded.append({"player_id": int(leg["player_id"]), "stat": leg["stat"], "side": leg["side"],
                       "line": float(leg["line"]), "actual": actual, "status": status,
                       "note": _minutes_note(int(leg["player_id"]), played, usual, logs_in)
                       if status in (MISSED, VOID) else ""})
    statuses = [g["status"] for g in graded]
    counting = [s for s in statuses if s != VOID]
    overall = (PENDING if PENDING in statuses else MISSED if MISSED in statuses
               else HIT if counting else VOID)
    return {"date": date, "status": overall, "legs": graded,
            "hit": statuses.count(HIT), "missed": statuses.count(MISSED)}
