import pandas as pd
import pytest

from edgefinder.models import nba_context


def box(game_id, date, team, opponent, players, season="2025-26", pts=15, minutes=30.0,
        fga=12, fta=4, tov=2):
    """One team's side of a game. `players` is a list of (player_id, minutes, pts)."""
    return [{"player_id": pid, "player_name": f"P{pid}", "team": team, "opponent": opponent,
             "game_id": game_id, "game_date": pd.Timestamp(date), "season": season,
             "minutes": m, "pts": p, "fga": fga, "fta": fta, "tov": tov, "is_home": team == "AAA"}
            for pid, m, p in players]


def frame(*boxes):
    return pd.DataFrame([row for b in boxes for row in b])


# team AAA: p1 and p2 are rotation players, p3 is a deep bench player; BBB is the opponent
FULL = [(1, 32.0, 20.0), (2, 30.0, 18.0), (3, 8.0, 2.0)]
WITHOUT_P2 = [(1, 36.0, 24.0), (3, 8.0, 2.0)]
OPP = [(10, 30.0, 15.0), (11, 28.0, 12.0)]


def three_games():
    return frame(
        box("g1", "2025-11-01", "AAA", "BBB", FULL), box("g1", "2025-11-01", "BBB", "AAA", OPP),
        box("g2", "2025-11-03", "AAA", "BBB", WITHOUT_P2), box("g2", "2025-11-03", "BBB", "AAA", OPP),
        box("g3", "2025-11-05", "AAA", "BBB", FULL), box("g3", "2025-11-05", "BBB", "AAA", OPP))


def lost(table, team, game_id):
    return table[(table["team"] == team) & (table["game_id"] == game_id)].iloc[0]


def test_the_first_game_has_nobody_lost_because_there_is_no_history_yet():
    row = lost(nba_context.absence_table(three_games()), "AAA", "g1")
    assert row["lost_min"] == 0.0 and row["n_absent"] == 0.0


def test_a_missing_rotation_player_costs_his_typical_minutes_and_points():
    row = lost(nba_context.absence_table(three_games()), "AAA", "g2")
    assert row["lost_min"] == pytest.approx(30.0)                 # p2's typical minutes
    assert row["lost_pts"] == pytest.approx(18.0)
    assert row["lost_starters"] == 1.0 and row["n_absent"] == 1.0


def test_a_deep_bench_player_who_is_missing_does_not_count():
    games = frame(
        box("g1", "2025-11-01", "AAA", "BBB", FULL), box("g1", "2025-11-01", "BBB", "AAA", OPP),
        box("g2", "2025-11-03", "AAA", "BBB", [(1, 32.0, 20.0), (2, 30.0, 18.0)]),   # p3 out
        box("g2", "2025-11-03", "BBB", "AAA", OPP))
    row = lost(nba_context.absence_table(games), "AAA", "g2")
    assert row["lost_min"] == 0.0 and row["n_absent"] == 0.0     # p3 normally plays 8 minutes


def test_a_returning_player_stops_counting_as_lost():
    row = lost(nba_context.absence_table(three_games()), "AAA", "g3")
    assert row["lost_min"] == 0.0 and row["n_absent"] == 0.0


def test_the_numbers_for_a_game_never_use_that_games_own_box_score():
    base = three_games()
    changed = base.copy()
    changed.loc[(changed["game_id"] == "g2") & (changed["player_id"] == 1), "minutes"] = 5.0
    before = lost(nba_context.absence_table(base), "AAA", "g2")
    after = lost(nba_context.absence_table(changed), "AAA", "g2")
    assert before["lost_min"] == after["lost_min"]


def test_a_players_typical_minutes_follow_a_weighted_average_of_his_games():
    games = frame(
        box("g1", "2025-11-01", "AAA", "BBB", [(1, 30.0, 10.0), (2, 30.0, 10.0)]),
        box("g1", "2025-11-01", "BBB", "AAA", OPP),
        box("g2", "2025-11-03", "AAA", "BBB", [(1, 40.0, 10.0), (2, 30.0, 10.0)]),
        box("g2", "2025-11-03", "BBB", "AAA", OPP),
        box("g3", "2025-11-05", "AAA", "BBB", [(2, 30.0, 10.0)]),                     # p1 out
        box("g3", "2025-11-05", "BBB", "AAA", OPP))
    row = lost(nba_context.absence_table(games), "AAA", "g3")
    expected = nba_context.EWM_ALPHA * 40.0 + (1 - nba_context.EWM_ALPHA) * 30.0       # 32.0
    assert row["lost_min"] == pytest.approx(expected)


def test_a_player_traded_away_stops_counting_once_he_leaves_the_recent_roster():
    games = [box("g0", "2025-10-01", "AAA", "BBB", FULL), box("g0", "2025-10-01", "BBB", "AAA", OPP)]
    day = pd.Timestamp("2025-10-03")
    for index in range(1, nba_context.ROSTER_WINDOW + 2):
        date = (day + pd.Timedelta(days=2 * index)).strftime("%Y-%m-%d")
        games.append(box(f"g{index}", date, "AAA", "BBB", [(1, 32.0, 20.0), (3, 8.0, 2.0)]))
        games.append(box(f"g{index}", date, "BBB", "AAA", OPP))
    table = nba_context.absence_table(frame(*games))
    assert lost(table, "AAA", "g1")["n_absent"] == 1.0            # p2 just left: still counted
    assert lost(table, "AAA", f"g{nba_context.ROSTER_WINDOW + 1}")["n_absent"] == 0.0   # long gone


def test_team_games_add_up_each_sides_points_and_what_it_allowed():
    table = nba_context.team_games(three_games())
    first = table[(table["team"] == "AAA") & (table["game_id"] == "g1")].iloc[0]
    assert first["pts"] == 40.0                                    # 20 + 18 + 2
    assert first["pts_against"] == 27.0                            # BBB scored 15 + 12
    assert first["poss"] == pytest.approx(3 * (12 + 0.44 * 4 + 2))


def test_a_teams_form_before_a_game_never_includes_that_game():
    games = pd.concat([three_games()], ignore_index=True)
    form = nba_context.team_form(nba_context.team_games(games))
    mine = form[form["team"] == "AAA"].sort_values("game_date")
    assert mine["pf10"].isna().all()                               # under 3 earlier games: nothing yet


def test_form_averages_only_the_games_before_and_waits_for_enough_history():
    boxes = []
    for index in range(5):
        date = f"2025-11-{index * 2 + 1:02d}"
        scoring = 10.0 * (index + 1)
        boxes += [box(f"g{index}", date, "AAA", "BBB", [(1, 30.0, scoring)]),
                  box(f"g{index}", date, "BBB", "AAA", [(10, 30.0, 8.0)])]
    form = nba_context.team_form(nba_context.team_games(frame(*boxes)))
    mine = form[form["team"] == "AAA"].sort_values("game_date").reset_index(drop=True)
    assert mine["pf10"].iloc[:3].isna().all()
    assert mine["pf10"].iloc[3] == pytest.approx((10 + 20 + 30) / 3)    # games 0-2 only
    assert mine["pf10"].iloc[4] == pytest.approx((10 + 20 + 30 + 40) / 4)


def test_adding_context_keeps_every_row_and_its_order():
    games = three_games()
    features = games[["player_id", "team", "opponent", "game_id", "game_date"]].copy()
    enriched = nba_context.add_context(features, games)
    assert len(enriched) == len(features)
    assert list(enriched["player_id"]) == list(features["player_id"])
    assert set(nba_context.CONTEXT_COLUMNS) <= set(enriched.columns)


def test_a_weak_defense_reads_above_one_and_a_strong_one_below_one():
    # DDD always allows 30 and CCC always allows 10; every team that scores against
    # them is EEE or FFF. Before the last day the league averages (30+20+10+20)/4 = 20.
    boxes = []
    for index in range(6):
        date = f"2025-11-{index * 2 + 1:02d}"
        boxes += [box(f"e{index}", date, "EEE", "DDD", [(1, 30.0, 30.0)]),
                  box(f"e{index}", date, "DDD", "EEE", [(2, 30.0, 20.0)]),
                  box(f"f{index}", date, "FFF", "CCC", [(3, 30.0, 10.0)]),
                  box(f"f{index}", date, "CCC", "FFF", [(4, 30.0, 20.0)])]
    boxes += [box("z", "2025-12-01", "EEE", "DDD", [(1, 30.0, 30.0)]),
              box("z", "2025-12-01", "DDD", "EEE", [(2, 30.0, 20.0)]),
              box("y", "2025-12-01", "FFF", "CCC", [(3, 30.0, 10.0)]),
              box("y", "2025-12-01", "CCC", "FFF", [(4, 30.0, 20.0)])]
    games = frame(*boxes)
    features = games[["player_id", "team", "opponent", "game_id", "game_date"]].copy()
    enriched = nba_context.add_context(features, games).set_index(["player_id", "game_id"])
    assert enriched.loc[(1, "z"), "opp_def_rel"] == pytest.approx(30.0 / 20.0)   # soft defense
    assert enriched.loc[(3, "y"), "opp_def_rel"] == pytest.approx(10.0 / 20.0)   # tough defense


def test_pace_reads_above_one_when_both_teams_play_fast():
    boxes = []
    for index in range(5):
        date = f"2025-11-{index * 2 + 1:02d}"
        # FAST and QUICK take 30 shots a game; SLOW and SLUG take 10
        boxes += [box(f"p{index}", date, "FAS", "QUI", [(1, 30.0, 20.0)], fga=30),
                  box(f"p{index}", date, "QUI", "FAS", [(2, 30.0, 20.0)], fga=30),
                  box(f"q{index}", date, "SLO", "SLU", [(3, 30.0, 20.0)], fga=10),
                  box(f"q{index}", date, "SLU", "SLO", [(4, 30.0, 20.0)], fga=10)]
    boxes += [box("fast", "2025-12-01", "FAS", "QUI", [(1, 30.0, 20.0)], fga=30),
              box("fast", "2025-12-01", "QUI", "FAS", [(2, 30.0, 20.0)], fga=30),
              box("slow", "2025-12-01", "SLO", "SLU", [(3, 30.0, 20.0)], fga=10),
              box("slow", "2025-12-01", "SLU", "SLO", [(4, 30.0, 20.0)], fga=10)]
    games = frame(*boxes)
    features = games[["player_id", "team", "opponent", "game_id", "game_date"]].copy()
    enriched = nba_context.add_context(features, games).set_index(["player_id", "game_id"])
    assert enriched.loc[(1, "fast"), "pace_rel"] > 1.0
    assert enriched.loc[(3, "slow"), "pace_rel"] < 1.0


def test_tonights_slate_reads_who_is_out_from_the_injury_report():
    context = nba_context.slate_context(three_games(), "2025-11-07",
                                        {"AAA": "BBB", "BBB": "AAA"}, out_ids={2})
    assert context["AAA"]["lost_min"] == pytest.approx(30.0)
    assert context["AAA"]["n_absent"] == 1.0
    assert context["BBB"]["lost_min"] == 0.0


def test_nobody_out_means_nothing_lost():
    context = nba_context.slate_context(three_games(), "2025-11-07",
                                        {"AAA": "BBB", "BBB": "AAA"}, out_ids=set())
    assert context["AAA"]["lost_min"] == 0.0


def test_a_player_who_is_out_but_not_on_the_recent_roster_is_ignored():
    context = nba_context.slate_context(three_games(), "2025-11-07",
                                        {"AAA": "BBB", "BBB": "AAA"}, out_ids={999})
    assert context["AAA"]["n_absent"] == 0.0


def test_the_slate_only_uses_games_before_its_date():
    early = nba_context.slate_context(three_games(), "2025-11-02",
                                      {"AAA": "BBB", "BBB": "AAA"}, out_ids={2})
    assert early["AAA"]["lost_min"] == pytest.approx(30.0)         # only game one is known
    assert early["AAA"]["n_absent"] == 1.0


def test_with_enough_team_history_the_slate_has_opponent_and_pace_numbers():
    context = nba_context.slate_context(three_games(), "2025-11-07",
                                        {"AAA": "BBB", "BBB": "AAA"}, out_ids=set())
    assert pd.notna(context["AAA"]["opp_def_rel"]) and pd.notna(context["AAA"]["pace_rel"])


def test_without_enough_team_history_the_opponent_numbers_are_missing_not_guessed():
    fewer = nba_context.slate_context(three_games(), "2025-11-02",
                                      {"AAA": "BBB", "BBB": "AAA"}, out_ids=set())
    assert pd.isna(fewer["AAA"]["opp_def_rel"]) and pd.isna(fewer["AAA"]["pace_rel"])
