"""The Picks screen's data: what each model would bet on a FanDuel game day, and every line with
each model's projection beside FanDuel's own price. Read-only, from the recorded ledger."""

import pandas as pd

from ..tracking import nba_paper, nba_parlay, nba_view
from . import service


def _fanduel() -> pd.DataFrame:
    return nba_paper.scope(service.load_ledger(), book=nba_paper.DEFAULT_BOOK)


def picks(date: str | None = None) -> dict:
    ledger = _fanduel()
    dates = nba_view.game_dates(ledger)
    if not dates:
        raise service.NotFound("no FanDuel lines recorded yet")
    date = date or dates[0]
    if date not in dates:
        raise service.NotFound(f"no FanDuel lines on {date}")
    day = ledger[ledger["game_date"] == date]
    ids = dict(zip(day["player"], day["player_id"].astype(int)))
    versions = sorted(day["model_version"].dropna().unique(), reverse=True)

    suggestions = nba_view.suggestions(ledger, date)
    liked = []
    for pick in suggestions.to_dict("records"):
        player, bet = pick["Bet"].split(" · ", 1)
        liked.append({"player": player, "player_id": int(pick["player_id"]),
                      "photo": nba_parlay.headshot_url(pick["player_id"]), "bet": bet,
                      "game_short": nba_view.short_game(pick["Game"]), "odds": int(pick["Odds"]),
                      "projects": service._num(pick["Model projects"], 1),
                      "ev_pct": service._num(pick["EV %"], 1), "agree": int(pick["Agree"])})

    table = nba_view.lines_for_date(ledger, date)
    lines = []
    for row in table.to_dict("records"):
        pid = ids.get(row["Player"])
        lines.append({
            "player": row["Player"], "player_id": pid,
            "photo": nba_parlay.headshot_url(pid) if pid else None,
            "game_short": nba_view.short_game(row["Game"]), "line": float(row["Line"]),
            "gap": service._num(row["Gap"], 1),
            "market_pct": service._num(row["Market P(over)"] * 100, 0),
            "over": int(row["Over odds"]), "under": int(row["Under odds"]),
            "models": [{"id": v, "proj": service._num(row.get(f"{v} proj"), 1),
                        "pct": service._num((row.get(f"{v} P(over)") or 0) * 100, 0)
                        if row.get(f"{v} proj") is not None else None,
                        "pick": row.get(f"{v} pick") or ""} for v in versions],
        })
    return {
        "date": date,
        "days": [{"date": d, "label": nba_view.day_label(d, service.today())} for d in dates],
        "models": [{"id": v, "short": service.model_short(v),
                    "name": service.model_name(v)} for v in versions],
        "liked": liked, "lines": lines,
    }
