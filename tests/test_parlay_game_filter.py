import pandas as pd

from edgefinder.ui import nba_parlay_tab as tab


def table():
    return pd.DataFrame({
        "Game": ["Heat @ Warriors", "Heat @ Warriors", "Magic @ Suns", "Magic @ Suns"],
        "away_abbr": ["MIA", "MIA", "ORL", "ORL"], "home_abbr": ["GSW", "GSW", "PHX", "PHX"],
        "Player": ["A", "B", "C", "D"]}, index=[10, 11, 12, 13])


def test_all_games_shows_everything_and_is_not_a_single_game(monkeypatch):
    monkeypatch.setattr(tab.style, "choose", lambda label, options, key, **kw: tab.ALL_GAMES)
    shown, single = tab._game_filter(table())
    assert single is False and list(shown.index) == [10, 11, 12, 13]


def test_one_game_keeps_only_its_legs_with_their_positions_in_the_full_table(monkeypatch):
    monkeypatch.setattr(tab.style, "choose", lambda label, options, key, **kw: "Magic @ Suns")
    shown, single = tab._game_filter(table())
    assert single is True and list(shown.index) == [12, 13]      # the slip still refers to 12, 13


def test_the_chooser_offers_all_games_first_then_each_game_with_short_names(monkeypatch):
    seen = {}

    def choose(label, options, key, format_func=str, **kw):
        seen.update(label=label, options=options, key=key,
                    names=[format_func(o) for o in options])
        return options[0]

    monkeypatch.setattr(tab.style, "choose", choose)
    tab._game_filter(table())
    assert seen["options"] == ["All games", "Heat @ Warriors", "Magic @ Suns"]
    assert seen["names"] == ["All games", "MIA @ GSW", "ORL @ PHX"]
    assert seen["key"] == "browse_game"
