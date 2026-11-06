import re

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


def test_the_narrow_screen_rules_come_last_so_they_override_the_base_rules():
    css = style.CSS
    assert css.index("@media (max-width: 900px)") > css.index('stColumn"]:has(.st-key-slip-panel)')
    assert css.index("@media (max-width: 640px)") > css.index(".bk-slip-big {")
    assert css.rstrip().endswith("</style>")
    # nothing but the closing tag may follow the last media block
    assert "{" not in css[css.rindex("}") + 1:]


def test_stickiness_is_set_on_the_wrapper_that_can_actually_travel():
    # the keyed container's own parent is only as tall as the bar, so sticky must be put
    # on that wrapper, and on the whole column for the side-by-side slip
    css = style.CSS
    assert 'stLayoutWrapper"]:has(> .st-key-slip-bar)' in css
    assert 'stColumn"]:has(.st-key-slip-panel)' in css
    assert "align-self: flex-start" in css
    column_rule = re.search(r'stColumn"\]:has\(\.st-key-slip-panel\) \{([^}]*)\}', css).group(1)
    assert "padding-bottom" in column_rule        # so the last card isn't clipped


def test_a_team_color_shows_on_the_card_edge_and_the_logo_beside_the_name():
    html = style.leg_card("p.png", "Jalen Brunson", "Over 24.5", "-106", accent="#F58426",
                          logo="https://cdn.nba.com/logos/knicks.svg")
    assert "border-left-color:#F58426" in html
    assert 'class="bk-tiny-logo"' in html and "knicks.svg" in html


def test_the_player_is_a_plain_cutout_with_nothing_behind_or_around_him():
    for html in (style.leg_card("p.png", "t", "s", "p", accent="#F58426"),
                 style.leader_card("p.png", "t", "PHI", "Points", 20, accent="#F58426"),
                 style.player_banner("n", "p.png", "", "s", "#F58426")):
        assert "gradient(160deg" not in html and "border-radius:50%" not in html
        assert '<img class="bk-photo' in html or '<img class="bk-banner-photo"' in html
    rule = re.search(r"(?m)^\.bk-photo \{([^}]*)\}", style.CSS).group(1)
    assert "border-radius" not in rule and "background" not in rule
    assert "object-fit: contain" in rule
    assert "border-radius: 50%" not in style.CSS


def test_a_status_colour_wins_over_the_team_color_on_the_card_edge():
    html = style.leg_card("p.png", "t", "s", "Hit", kind="hit", accent="#F58426")
    assert "border-left-color" not in html and 'class="bk-card hit"' in html


def test_a_bad_color_value_is_ignored_instead_of_reaching_the_page():
    for bad in ('red" onerror="x', "#12", "url(javascript:x)", "<b>"):
        html = style.leg_card("p.png", "t", "s", "p", accent=bad)
        assert "onerror" not in html and "javascript" not in html and "linear-gradient" not in html
        assert "<b>" not in html and "border-left-color" not in html


def test_a_game_card_colors_each_teams_edge_and_works_without_colors():
    colored = style.game_card("CHI", "NYK", "a.svg", "b.svg", 28, 53, "Q2", "live",
                              "#CE1141", "#F58426")
    assert "border-left-color:#CE1141" in colored and "border-left-color:#F58426" in colored
    plain = style.game_card("CHI", "NYK", "a.svg", "b.svg", 28, 53, "Q2", "live")
    assert "border-left-color" not in plain


def test_comparison_bars_use_each_teams_color_with_defaults_when_none_given():
    colored = style.compare_bar("Rebounds", "13", "10", 0.57, "away", "#CE1141", "#F58426")
    assert "background:#CE1141" in colored and "background:#F58426" in colored
    assert "background:" in style.compare_bar("Rebounds", "13", "10", 0.57, "away")


def test_the_player_banner_shows_name_logo_and_team_tint_safely():
    html = style.player_banner("Jalen <Brunson>", "p.png", "logo.svg", "NYK · 7 games", "#F58426")
    assert "Jalen &lt;Brunson&gt;" in html and "<Brunson>" not in html
    assert "rgba(245,132,38" in html and "logo.svg" in html and "NYK · 7 games" in html
    assert "rgba(239,243,244" in style.player_banner("n", "p", "", "s", "not a color")


def test_a_stat_tile_shows_its_number_and_label():
    html = style.stat_tile("Points", "24.6", "#F58426")
    assert "24.6" in html and "Points" in html and "border-top-color:#F58426" in html


def test_a_notice_and_a_footer_escape_their_text():
    assert "&lt;b&gt;" in style.notice("<b>careful</b>") and "<b>" not in style.notice("<b>")
    html = style.footer(["line <one>", "line & two"])
    assert "line &lt;one&gt;<br>line &amp; two" in html


def test_the_empty_slip_message_is_escaped_and_shown():
    html = style.empty_slip("Empty <b>", "Tap & add")
    assert "Empty &lt;b&gt;" in html and "Tap &amp; add" in html and "<b>" not in html


def test_a_missing_logo_leaves_no_broken_image():
    assert "<img" not in style.game_card("A", "B", "", "", 1, 2, "Q1", "live")


def test_html_has_no_indented_lines_that_markdown_would_treat_as_code():
    html = style.slip_summary("H", "B", [("k", "v")]) + style.leg_card("u", "t", "s", "p")
    assert "\n    " not in html


def test_an_idea_card_lists_each_leg_and_the_chance_and_payout_safely():
    html = style.idea_card([("a.png", "A.J. <Green>", "10+ points", "+120"),
                            ("b.png", "Jaylen Brown", "16+ points", "-110")], "20%", "$6.12")
    assert html.count('class="bk-leg"') == 2
    assert "A.J. &lt;Green&gt;" in html and "<Green>" not in html
    assert "<b>20%</b> to hit" in html and "<b>$6.12</b> back on $1" in html


def test_short_model_names_are_one_word_and_unknown_versions_pass_through():
    from edgefinder.tracking import nba_parlay
    assert nba_parlay.short_model_name("context-v1") == "Smartest"
    assert nba_parlay.short_model_name("minutes-v1") == "Smarter"
    assert nba_parlay.short_model_name("ewma-v1") == "Simple"
    assert nba_parlay.short_model_name("future-v9") == "future-v9"


def test_links_and_alert_boxes_follow_the_black_palette_not_streamlits_blue():
    assert ".stApp a, .stApp a:visited" in style.CSS
    assert 'stAlertContainer"] {' in style.CSS
    assert "1493FF" not in style.CSS.upper() and "3D9DF3" not in style.CSS.upper()


def test_a_team_that_just_scored_flashes_and_shows_how_many_points():
    live = style.game_card("CHI", "NYK", "a.svg", "b.svg", 31, 28, "Q2", "live", "", "", 3, 0)
    assert live.count("bk-pop") == 1 and "+3" in live and "p3" in live
    assert live.count("scored") == 1 and live.index("scored") < live.index("CHI")
    two = style.game_card("CHI", "NYK", "a.svg", "b.svg", 31, 28, "Q2", "live", "", "", 0, 2)
    assert "+2" in two and "p2" in two and two.index("scored") > two.index("CHI")


def test_nothing_pops_when_nobody_scored_or_the_game_has_not_started():
    assert "bk-pop" not in style.game_card("A", "B", "", "", 10, 8, "Q1", "live")
    assert "scored" not in style.game_card("A", "B", "", "", 10, 8, "Q1", "live", "", "", 0, 0)
    assert "bk-pop" not in style.game_card("A", "B", "", "", 0, 0, "8 pm", "upcoming",
                                            "", "", 3, 3)


def test_the_basket_animation_is_defined_and_switched_off_for_reduced_motion():
    css = style.CSS
    assert "@keyframes bk-rise" in css and "@keyframes bk-flash" in css
    assert "prefers-reduced-motion: reduce" in css
    block = css[css.index("prefers-reduced-motion: reduce"):]
    assert "animation: none" in block[:200]
