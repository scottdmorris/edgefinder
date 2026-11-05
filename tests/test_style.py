from edgefinder.ui import style


def test_text_from_data_is_escaped_so_it_cannot_inject_html():
    html = style.leg_card("https://cdn.nba.com/x.png", '<script>alert(1)</script>',
                          'A & B "game"', "<b>+110</b>")
    assert "<script>" not in html and "<b>" not in html
    assert "&lt;script&gt;" in html and "A &amp; B" in html


def test_a_photo_url_cannot_break_out_of_its_attribute():
    html = style.leg_card('https://x/y.png" onerror="alert(1)', "t", "s", "+100")
    assert 'onerror="alert' not in html


def test_progress_is_clamped_to_a_valid_bar_width():
    assert "width:100%" in style.leg_card("u", "t", "s", "p", progress=3.0)
    assert "width:0%" in style.leg_card("u", "t", "s", "p", progress=-1.0)
    assert "width:40%" in style.leg_card("u", "t", "s", "p", progress=0.4)
    assert "bk-bar" not in style.leg_card("u", "t", "s", "p")


def test_a_compact_card_is_marked_so_it_can_shrink_for_the_slip():
    assert "bk-card  compact" in style.leg_card("u", "t", "s", "p", compact=True)
    assert "compact" not in style.leg_card("u", "t", "s", "p")
    assert 'class="bk-card hit compact"' in style.leg_card("u", "t", "s", "p", kind="hit",
                                                            compact=True)


def test_the_status_colours_the_card_and_its_pill():
    html = style.leg_card("u", "t", "s", "Hit", kind="hit")
    assert 'class="bk-card hit"' in html and 'class="bk-pill hit"' in html


def test_the_slip_summary_shows_the_headline_and_each_fact():
    html = style.slip_summary("TO WIN", "$30.00", [("Stake", "$10.00"), ("Chance", "12%")])
    assert "TO WIN" in html and "$30.00" in html and "Stake" in html and "12%" in html


def test_a_feed_item_escapes_the_play_text():
    html = style.feed_item("Q2 5:10", "Smith <makes> 3", "CHI 28 - NYK 53")
    assert "&lt;makes&gt;" in html and "<makes>" not in html


def test_the_leading_team_is_highlighted_and_scores_hide_before_tip_off():
    live = style.game_card("CHI", "NYK", "a.svg", "b.svg", 28, 53, "2nd Qtr 9:13", "live")
    assert live.count("bk-team lead") == 1
    assert live.index("NYK") > live.index("bk-team lead")        # the home team leads
    assert "28" in live and "53" in live and "bk-game live" in live
    upcoming = style.game_card("CHI", "NYK", "a.svg", "b.svg", 0, 0, "8:00 pm ET", "upcoming")
    assert "lead" not in upcoming and "–" in upcoming


def test_a_tied_game_highlights_neither_team():
    assert "bk-team lead" not in style.game_card("A", "B", "", "", 50, 50, "Q3", "live")


def test_a_comparison_bar_splits_by_share_and_highlights_the_leader():
    html = style.compare_bar("Rebounds", "13", "10", 13 / 23, "away")
    assert "width:57%" in html and "width:43%" in html
    assert html.count("lead") == 1 and html.index("lead") < html.index("Rebounds")


def test_a_tied_comparison_highlights_neither_side():
    assert "lead" not in style.compare_bar("Assists", "10", "10", 0.5, "")


def test_comparison_text_is_escaped():
    html = style.compare_bar("<b>x</b>", "<i>", "&", 0.5, "")
    assert "<b>" not in html and "<i>" not in html and "&lt;b&gt;" in html


def test_a_leader_card_shows_the_player_team_and_number():
    html = style.leader_card("p.png", "Tyrese <Maxey>", "PHI", "PTS", 18)
    assert "Tyrese &lt;Maxey&gt;" in html and "18" in html and "PTS" in html


def test_timeout_dots_show_how_many_are_left_and_never_go_out_of_range():
    assert style.dots(3, 7) == "●●●○○○○"
    assert style.dots(0, 7) == "○○○○○○○"
    assert style.dots(9, 7) == "●●●●●●●" and style.dots(-2, 7) == "○○○○○○○"


def test_the_empty_slip_message_is_escaped_and_shown():
    html = style.empty_slip("Empty <b>", "Tap & add")
    assert "Empty &lt;b&gt;" in html and "Tap &amp; add" in html and "<b>" not in html


def test_a_missing_logo_leaves_no_broken_image():
    assert "<img" not in style.game_card("A", "B", "", "", 1, 2, "Q1", "live")


def test_html_has_no_indented_lines_that_markdown_would_treat_as_code():
    html = style.slip_summary("H", "B", [("k", "v")]) + style.leg_card("u", "t", "s", "p")
    assert "\n    " not in html
