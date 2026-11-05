import dataclasses
import pathlib

import pandas as pd
import pytest

from edgefinder.tracking import nba_player_lookup as lookup
from edgefinder.tracking import nba_questions as q


def rows(player_id, name, team, season, start, pts, reb=None, ast=None, fg3m=None, home=None):
    """One player's games on consecutive days from `start`."""
    out = []
    for i, p in enumerate(pts):
        out.append({
            "player_id": player_id, "player_name": name, "team": team,
            "game_date": pd.Timestamp(start) + pd.Timedelta(days=i), "season": season,
            "minutes": 30.0, "pts": p,
            "reb": reb[i] if reb else 4, "ast": ast[i] if ast else 3,
            "fg3m": fg3m[i] if fg3m else 1, "opponent": "MIL",
            "is_home": home[i] if home else True, "wl": "W"})
    return out


T, F = True, False
GAMES = pd.DataFrame(
    # Brunson: 10 games this season (home on odd days), plus two big games last season.
    rows(2, "Jalen Brunson", "NYK", "2024-25", "2024-11-01", [40, 40])
    + rows(2, "Jalen Brunson", "NYK", "2025-26", "2025-11-01",
           [20, 24, 30, 24, 18, 26, 24, 35, 22, 28],
           reb=[3, 4, 5, 2, 6, 3, 4, 7, 2, 3], ast=[8, 9, 6, 10, 7, 5, 9, 11, 8, 6],
           fg3m=[2, 3, 1, 0, 4, 2, 3, 5, 1, 2], home=[T, F] * 5)
    + rows(5, "Nikola Jokić", "DEN", "2025-26", "2025-11-01", [25] * 6,
           reb=[12, 9, 10, 14, 8, 11])
    + rows(3, "Luka Dončić", "LAL", "2025-26", "2025-11-01", [30, 35, 28, 40])
    + rows(1, "Jaylen Brown", "BOS", "2025-26", "2025-11-01", [22, 18, 25, 19, 15, 21],
           home=[T, T, F, T, F, T])
    + rows(4, "Gary Trent Jr.", "TOR", "2025-26", "2025-11-01", [12, 15, 9], home=[F, F, F])
    + rows(6, "Keldon Johnson", "SAS", "2025-26", "2025-11-01", [14, 20])
    + rows(7, "Jalen Johnson", "ATL", "2025-26", "2025-11-01", [22, 25, 28])
    + rows(8, "Rudy Gay", "UTA", "2024-25", "2024-11-01", [8])
    + rows(9, "Marcus Morris Sr.", "LAC", "2025-26", "2025-11-01", [10, 12])
    + rows(10, "Marcus Morris Jr.", "DET", "2025-26", "2025-11-01", [11, 13])
    + rows(11, "Mark Williams", "PHX", "2025-26", "2025-11-01", [8, 12, 14])
    + rows(12, "Mark Williamson", "MEM", "2025-26", "2025-11-01", [2, 3])
)

# question, count, games considered, pushes -- every number checked by hand
# (Brunson this season: pts 20 24 30 24 18 26 24 35 22 28, home on games 1,3,5,7,9).
GOLDEN = [
    ("How often has Brunson scored over 24 in his last 10?", 4, 10, 3),
    ("Brunson over 24 points in his last 5", 3, 5, 1),               # 26 24 35 22 28
    ("Brunson 24+ points last 10", 7, 10, 0),
    ("Brunson at least 24 points in his last 5 games", 4, 5, 0),
    ("Brunson under 24 points last 10", 3, 10, 3),
    ("Brunson at most 20 points this season", 2, 10, 0),
    ("Brunson over 24.5 points last 10", 4, 10, 0),           # no push on a half line
    ("Brunson under 22.5 points at home", 3, 5, 0),           # home: 20 30 18 24 22
    ("Brunson over 24 points on the road", 3, 5, 2),          # away: 24 24 26 35 28
    ("Brunson 5+ rebounds this season", 3, 10, 0),
    ("Brunson over 8.5 assists last 10", 4, 10, 0),
    ("Brunson 3+ threes this season", 4, 10, 0),
    ("Brunson more than 2.5 three-pointers last 10", 4, 10, 0),
    ("Brunson's points over 24 last 10", 4, 10, 3),
    ("brunson OVER 24 POINTS LAST 10", 4, 10, 3),
    ("Brunson scored fewer than 21 in his last 10", 2, 10, 0),
    ("Did Brunson score at least 30 this season?", 2, 10, 0),
    ("Brunson over 40 points last 10", 0, 10, 0),             # zero hits is still an answer
    ("How many times did Brunson get 10+ assists in his last 10", 2, 10, 0),
    ("Brunson at most 3 rebounds last 5", 3, 5, 0),          # 3 4 7 2 3
    ("Did Jokic get 10+ rebounds this season?", 4, 6, 0),
    ("Jokić over 9.5 rebounds", 4, 6, 0),
    ("Doncic points over 29.5", 3, 4, 0),
    ("Luka Doncic under 30 points this season", 1, 4, 1),
    ("Brown points under 19.5 at home", 2, 4, 0),             # home: 22 18 19 21
    ("Brown under 19 points at home", 1, 4, 1),
    ("Jaylen Brown 20+ points away", 1, 2, 0),               # away: 25 15
    ("Gary Trent Jr. over 10 points", 2, 3, 0),
    ("Trent Jr over 10 points in his last 10", 2, 3, 0),            # only 3 games on record
    ("gary trent over 10 points at home", 0, 0, 0),                 # he has no home games
    ("Rudy Gay over 5 points this season", 0, 0, 0),         # last played in 2024-25
    ("Mark Williams over 10 points", 2, 3, 0),               # whole word beats Williamson
    ("Keldon Johnson over 15 points", 1, 2, 0),
    ("Jalen Johnson 25+ points", 2, 3, 0),
    ("What percent of the time did Jalen Brunson hit 3+ threes in the last 4 games", 2, 4, 0),
]


@pytest.mark.parametrize("question,count,considered,pushes", GOLDEN)
def test_golden_questions(question, count, considered, pushes):
    result = q.ask(question, GAMES)
    assert isinstance(result, q.Answer), result
    assert (result.count, result.games_considered, result.pushes) == (count, considered, pushes)
    expected_pct = None if considered == 0 else count / considered * 100.0
    assert result.percentage == expected_pct
    assert len(result.games) == considered


def test_there_are_at_least_thirty_golden_questions():
    assert len(GOLDEN) >= 30


# ---- strictness ------------------------------------------------------------

def test_over_is_strict_and_a_plus_or_at_least_includes_the_line():
    assert q.parse("Brunson over 24", GAMES).reason == "no_stat"
    over = q.ask("Brunson points over 24 last 10", GAMES)
    plus = q.ask("Brunson 24+ points last 10", GAMES)
    at_least = q.ask("Brunson points at least 24 last 10", GAMES)
    assert over.count == 4 and plus.count == at_least.count == 7
    assert plus.count - over.count == 3          # exactly the three games on 24


def test_landing_on_a_whole_line_is_a_push_neither_over_nor_under():
    over = q.ask("Brunson over 24 points last 10", GAMES)
    under = q.ask("Brunson under 24 points last 10", GAMES)
    assert over.count + under.count + over.pushes == 10
    assert "neither over nor under" in over.summary
    assert "exactly 24" in over.summary


def test_a_half_line_can_never_push():
    result = q.ask("Brunson over 23.5 points last 10", GAMES)
    assert result.pushes == 0 and "neither" not in result.summary


def test_answers_match_the_existing_hit_rate_function():
    history = lookup.player_games(GAMES[GAMES["season"] == "2025-26"], 2)
    for line in (23.5, 24.0, 40.0):
        for last in (3, 10):
            expected = lookup.hit_rate(history, "pts", line, last=last)
            over = q.ask(f"Brunson over {line} points last {last}", GAMES)
            under = q.ask(f"Brunson under {line} points last {last}", GAMES)
            assert (over.count, under.count, over.games_considered) == \
                (expected["over"], expected["under"], expected["games"])
            assert over.percentage == pytest.approx(expected["over_pct"])


# ---- windows and defaults --------------------------------------------------

def test_no_window_means_this_season_and_ignores_last_seasons_games():
    result = q.ask("Brunson over 29 points", GAMES)       # his 2024-25 40s must not count
    assert result.games_considered == 10 and result.count == 2     # 30 and 35
    assert "2025-26 season" in result.summary


def test_last_n_takes_the_most_recent_games_in_date_order_even_if_rows_are_shuffled():
    shuffled = GAMES.sample(frac=1, random_state=3)
    result = q.ask("Brunson over 24 points last 2", shuffled)    # 22 then 28
    assert (result.count, result.games_considered) == (1, 2)
    assert list(result.games["Points"]) == [28, 22]               # newest first


def test_fewer_games_than_the_window_is_reported_not_hidden():
    result = q.ask("Trent over 10 points last 10", GAMES)
    assert result.games_considered == 3
    assert "Only 3 were on record, fewer than the 10 asked for" in result.summary


def test_last_n_with_home_filter_means_the_last_n_home_games():
    result = q.ask("Brunson under 23 points last 3 at home", GAMES)   # home: 18, 24, 22
    assert list(result.games["Points"]) == [22, 24, 18]
    assert (result.count, result.games_considered) == (2, 3)


def test_last_game_is_a_window_of_one():
    result = q.ask("Brunson over 25 points in his last game", GAMES)
    assert (result.count, result.games_considered) == (1, 1)       # 28


def test_a_window_with_no_games_says_so_instead_of_reporting_zero_percent():
    result = q.ask("Rudy Gay over 5 points this season", GAMES)
    assert result.percentage is None and result.games_considered == 0
    assert "nothing to count" in result.summary and "0%" not in result.summary


def test_missing_stat_values_are_not_counted_as_games():
    frame = GAMES.copy()
    frame.loc[frame["game_date"] == pd.Timestamp("2025-11-10"), "pts"] = None
    result = q.ask("Brunson over 24 points last 3", frame)           # 10th game has no value
    assert result.games_considered == 3 and list(result.games["Points"]) == [22, 35, 24]


# ---- the answer's shape ----------------------------------------------------

def test_the_summary_is_one_plain_sentence_with_the_numbers():
    result = q.ask("How often has Brunson scored over 24.5 in his last 10?", GAMES)
    assert result.summary == "Jalen Brunson had more than 24.5 points in 4 of the last 10 games (40%)."


def test_the_summary_for_a_home_season_question():
    result = q.ask("Brown points under 19.5 at home", GAMES)
    assert result.summary == ("Jaylen Brown had fewer than 19.5 points in 2 of 4 home games "
                              "in the 2025-26 season (50%).")


def test_the_games_table_lists_each_game_with_its_outcome():
    result = q.ask("Brown under 19 points at home", GAMES)
    table = result.games
    assert list(table.columns) == ["Date", "Opponent", "Result", "Points", "Outcome"]
    assert list(table["Points"]) == [21, 19, 18, 22]               # newest first
    assert list(table["Outcome"]) == ["Miss", "Push", "Hit", "Miss"]
    assert set(table["Opponent"]) == {"vs MIL"}


def test_the_answer_does_not_modify_the_games_given():
    before = GAMES.copy(deep=True)
    q.ask("Brunson over 24 points last 10", GAMES)
    pd.testing.assert_frame_equal(GAMES, before)


def test_answer_needs_the_game_log_columns():
    with pytest.raises(ValueError, match="missing columns"):
        q.answer(q.Query(player_id=2, stat="points", comparison="over", threshold=1),
                 GAMES.drop(columns=["is_home"]))


# ---- names -----------------------------------------------------------------

@pytest.mark.parametrize("question", ["Doncic over 29.5 points", "luka doncic over 29.5 points",
                                      "Dončić over 29.5 points", "LUKA DONČIĆ over 29.5 points"])
def test_names_ignore_accents_and_case(question):
    assert q.ask(question, GAMES).player_name == "Luka Dončić"


@pytest.mark.parametrize("question", ["Gary Trent Jr. over 10 points", "gary trent jr over 10 points",
                                      "Trent over 10 points", "Gary Trent over 10 points"])
def test_names_ignore_suffixes_whether_typed_or_not(question):
    assert q.ask(question, GAMES).player_name == "Gary Trent Jr."


def test_an_ambiguous_surname_asks_instead_of_picking():
    result = q.parse("Johnson over 20 points", GAMES)
    assert isinstance(result, q.ParseFailure) and result.reason == "ambiguous_player"
    assert set(result.candidates) == {"Keldon Johnson (SAS)", "Jalen Johnson (ATL)"}
    assert "which one" in result.message


def test_an_ambiguous_first_name_lists_everyone_who_matches():
    result = q.parse("Jalen over 20 points", GAMES)
    assert result.reason == "ambiguous_player"
    assert set(result.candidates) == {"Jalen Brunson (NYK)", "Jalen Johnson (ATL)"}


def test_two_players_with_the_same_name_apart_from_the_suffix_are_ambiguous():
    result = q.parse("Marcus Morris over 10 points", GAMES)
    assert result.reason == "ambiguous_player" and len(result.candidates) == 2
    assert q.ask("Marcus Morris Jr. over 12 points", GAMES).player_name == "Marcus Morris Jr."


def test_a_misspelled_name_offers_suggestions_but_never_answers():
    result = q.ask("Brunsen over 24 points", GAMES)
    assert isinstance(result, q.ParseFailure) and result.reason == "unknown_player"
    assert result.candidates == ("Jalen Brunson (NYK)",) and "Did you mean" in result.message


def test_an_unknown_player_is_refused_without_suggestions():
    result = q.ask("Zzzzzz over 24 points", GAMES)
    assert result.reason == "unknown_player" and result.candidates == ()


def test_a_missing_player_is_reported():
    result = q.parse("over 24 points last 10", GAMES)
    assert result.reason == "no_player"


def test_a_query_holding_a_name_resolves_it_when_answered():
    query = q.Query(player_text="Doncic", stat="points", comparison="over", threshold=29.5)
    assert q.answer(query, GAMES).count == 3
    ambiguous = q.Query(player_text="Johnson", stat="points", comparison="over", threshold=1)
    assert q.answer(ambiguous, GAMES).reason == "ambiguous_player"


# ---- numbers ---------------------------------------------------------------

def test_a_decimal_line_is_read_exactly():
    assert q.parse("Brunson points over 24.5", GAMES).threshold == 24.5


def test_numbers_must_be_digits_and_the_refusal_says_so():
    result = q.parse("Brunson over twenty points", GAMES)
    assert result.reason == "number_words" and "digits" in result.message
    assert q.parse("Brunson over 24 points in his last ten", GAMES).reason == "number_words"


def test_the_three_in_three_pointers_is_a_stat_not_a_line():
    for text in ("Brunson 3+ threes", "Brunson over 2.5 3-pointers", "Brunson over 2.5 3s",
                 "Brunson over 2.5 three pointers"):
        parsed = q.parse(text, GAMES)
        assert parsed.stat == "threes", text
    assert q.parse("Brunson over 2.5 3-pointers", GAMES).threshold == 2.5


# ---- unclear, conflicting and unsupported questions ------------------------

@pytest.mark.parametrize("question,reason", [
    ("Brunson over 24", "no_stat"),
    ("Brunson points 24", "no_comparison"),
    ("Brunson points over", "no_threshold"),
    ("Brunson over 24 or 25 points", "ambiguous_threshold"),
    ("Brunson over 24 points and rebounds", "ambiguous_stat"),
    ("Brunson over under 24 points", "conflicting_comparison"),
    ("Brunson over 24 points at least 20", "conflicting_comparison"),
    ("Brunson over 24 points at home and on the road", "conflicting_venue"),
    ("Brunson over 24 points last 0 games", "bad_window"),
    ("Brunson over 24 points last 2.5 games", "bad_window"),
    ("Brunson over 24 points last 5 this season", "conflicting_window"),
])
def test_unclear_questions_say_what_is_wrong(question, reason):
    result = q.parse(question, GAMES)
    assert isinstance(result, q.ParseFailure) and result.reason == reason
    assert reason in result.reasons and result.message


def test_every_problem_is_reported_at_once():
    result = q.parse("points", GAMES)
    assert result.reasons == ("no_player", "no_comparison", "no_threshold")


@pytest.mark.parametrize("question", [
    "Brunson over 24 points vs the Celtics", "Brunson career points over 24",
    "Brunson steals over 2", "Brunson points over 24 tonight",
    "Brunson average points last 10", "Brunson over 24 points last season",
    "Brunson points plus rebounds PRA over 40", "Brunson over 24 points in the playoffs",
])
def test_conditions_that_cannot_be_applied_are_refused_not_ignored(question):
    result = q.parse(question, GAMES)
    assert result.reason == "unsupported" and "Examples:" in result.message


@pytest.mark.parametrize("question", ["", "   ", None, "\n\t"])
def test_empty_input_asks_for_a_question(question):
    result = q.parse(question, GAMES)
    assert result.reason == "empty" and "Examples:" in result.message


@pytest.mark.parametrize("question", ["asdf qwerty", "What's the weather like?", "???", "hello"])
def test_nonsense_gets_the_list_of_what_can_be_asked(question):
    result = q.parse(question, GAMES)
    assert result.reason == "unsupported"
    assert result.supported == q.SUPPORTED_EXAMPLES and "points, rebounds, assists" in result.message


def test_the_supported_examples_all_parse():
    for example in q.SUPPORTED_EXAMPLES:
        if "Trent" in example:
            continue                                  # the "3+ threes road" fixture is Trent's
        assert isinstance(q.parse(example, GAMES), q.Query), example
    assert isinstance(q.parse("Gary Trent Jr. 3+ threes on the road", GAMES), q.Query)


# ---- the Query contract ----------------------------------------------------

def test_parse_returns_a_resolved_query():
    parsed = q.parse("How often has Brunson scored over 24 in his last 10?", GAMES)
    assert parsed == q.Query(player_id=2, stat="points", comparison="over", threshold=24.0,
                             window="last_n", last_n=10, venue=None)
    assert parsed.player_text is None


def test_query_round_trips_through_a_dict():
    original = q.Query(player_id=2, stat="threes", comparison="at_least", threshold=3,
                       window="last_n", last_n=5, venue="away")
    assert q.Query.from_dict(original.to_dict()) == original
    named = q.Query(player_text=" Doncic ", stat="points", comparison="under", threshold=29.5)
    assert q.Query.from_dict(named.to_dict()) == named and named.player_text == "Doncic"


def test_query_is_frozen():
    query = q.Query(player_id=2, stat="points", comparison="over", threshold=24)
    with pytest.raises(dataclasses.FrozenInstanceError):
        query.threshold = 5


GOOD = {"player_id": 2, "stat": "points", "comparison": "over", "threshold": 24}


@pytest.mark.parametrize("change", [
    {"stat": "steals"}, {"comparison": "above"}, {"threshold": -1}, {"threshold": float("nan")},
    {"threshold": float("inf")}, {"threshold": "24"}, {"threshold": True},
    {"window": "career"}, {"window": "last_n"}, {"window": "last_n", "last_n": 0},
    {"window": "last_n", "last_n": 2.5}, {"window": "last_n", "last_n": True},
    {"last_n": 5}, {"venue": "neutral"}, {"player_id": None}, {"player_id": "2"},
    {"player_text": "Brunson"}, {"player_id": None, "player_text": "  "},
    {"extra": 1}, {"stat": None},
])
def test_invalid_queries_are_rejected(change):
    with pytest.raises(ValueError):
        q.Query.from_dict({**GOOD, **change})


@pytest.mark.parametrize("missing", ["stat", "comparison", "threshold"])
def test_from_dict_names_missing_fields(missing):
    data = {k: v for k, v in GOOD.items() if k != missing}
    with pytest.raises(ValueError, match=missing):
        q.Query.from_dict(data)


def test_from_dict_rejects_things_that_are_not_mappings():
    for bad in (None, "points over 24", [1, 2]):
        with pytest.raises(ValueError):
            q.Query.from_dict(bad)


def test_numpy_numbers_are_accepted_and_normalised():
    import numpy as np
    query = q.Query(player_id=np.int64(2), stat="points", comparison="over",
                    threshold=np.float64(24), window="last_n", last_n=np.int64(3))
    assert type(query.player_id) is int and type(query.threshold) is float
    assert type(query.last_n) is int


def test_a_hand_built_query_answers_like_a_parsed_one():
    built = q.Query(player_id=2, stat="rebounds", comparison="at_least", threshold=5)
    assert q.answer(built, GAMES).count == q.ask("Brunson 5+ rebounds", GAMES).count == 3


def test_no_language_model_is_used():
    source = pathlib.Path(q.__file__).read_text(encoding="utf-8")
    for banned in ("anthropic", "openai", "requests", "urllib", "httpx"):
        assert banned not in source.lower()
