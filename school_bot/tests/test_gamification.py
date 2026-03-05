"""Tests for services/gamification.py — XP, streaks, badges, levels, themes."""
import pytest
from datetime import date, timedelta

from services.gamification import (
    xp_for_level,
    level_from_xp,
    get_level_name,
    progress_bar,
    calculate_xp,
    update_streak,
    check_badges,
    get_result_comment,
    format_results_text,
    format_gamification_header,
    get_theme,
    THEMES,
    BADGES,
)


# ---------------------------------------------------------------------------
# Level calculations
# ---------------------------------------------------------------------------

class TestLevels:
    def test_xp_for_level_1(self):
        assert xp_for_level(1) == 0

    def test_xp_for_level_2(self):
        assert xp_for_level(2) == 100

    def test_xp_for_level_3(self):
        assert xp_for_level(3) == 400

    def test_xp_for_level_5(self):
        assert xp_for_level(5) == 1600

    def test_xp_for_level_10(self):
        assert xp_for_level(10) == 8100

    def test_level_from_xp_zero(self):
        assert level_from_xp(0) == 1

    def test_level_from_xp_50(self):
        assert level_from_xp(50) == 1

    def test_level_from_xp_100(self):
        assert level_from_xp(100) == 2

    def test_level_from_xp_400(self):
        assert level_from_xp(400) == 3

    def test_level_from_xp_1600(self):
        assert level_from_xp(1600) == 5

    def test_level_name_neutral(self):
        name = get_level_name("neutral", 3)
        assert "3" in name

    def test_level_name_minecraft_level1(self):
        name = get_level_name("minecraft", 1)
        assert name == THEMES["minecraft"]["levels"][0]

    def test_level_name_capped(self):
        # Level beyond max should return last level name
        name = get_level_name("minecraft", 100)
        assert name == THEMES["minecraft"]["levels"][-1]


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

class TestProgressBar:
    def test_progress_bar_zero(self):
        bar = progress_bar(0, 10)
        assert "0%" in bar

    def test_progress_bar_half(self):
        bar = progress_bar(5, 10)
        assert "50%" in bar

    def test_progress_bar_full(self):
        bar = progress_bar(10, 10)
        assert "100%" in bar

    def test_progress_bar_zero_total(self):
        bar = progress_bar(0, 0)
        assert "0%" in bar


# ---------------------------------------------------------------------------
# XP calculation
# ---------------------------------------------------------------------------

class TestXPCalculation:
    def test_basic_xp(self):
        xp = calculate_xp(correct=5, total=10, streak_days=0)
        assert xp == 50  # 5 * 10

    def test_perfect_bonus(self):
        xp = calculate_xp(correct=10, total=10, streak_days=0)
        assert xp == 120  # 10*10 + 20 bonus

    def test_streak_bonus(self):
        xp = calculate_xp(correct=5, total=10, streak_days=3)
        assert xp == 65  # 50 + 15 streak

    def test_streak_bonus_capped(self):
        xp = calculate_xp(correct=5, total=10, streak_days=20)
        assert xp == 100  # 50 + 50 (capped)

    def test_speed_bonus(self):
        times = [3.0, 5.0, 8.0, 15.0, 20.0]  # 3 fast answers
        xp = calculate_xp(correct=3, total=5, streak_days=0, answer_times=times)
        assert xp == 45  # 30 + 15 speed bonus

    def test_all_bonuses(self):
        times = [3.0] * 5  # all fast
        xp = calculate_xp(correct=5, total=5, streak_days=5, answer_times=times)
        # 50 (correct) + 20 (perfect) + 25 (streak) + 25 (speed) = 120
        assert xp == 120

    def test_zero_correct(self):
        xp = calculate_xp(correct=0, total=10, streak_days=0)
        assert xp == 0


# ---------------------------------------------------------------------------
# Streak logic
# ---------------------------------------------------------------------------

class TestStreak:
    def test_first_quiz(self):
        streak, continued = update_streak(None, 0)
        assert streak == 1
        assert not continued

    def test_same_day(self):
        today = date.today().isoformat()
        streak, continued = update_streak(today, 5)
        assert streak == 5
        assert continued

    def test_consecutive_day(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        streak, continued = update_streak(yesterday, 5)
        assert streak == 6
        assert continued

    def test_streak_broken(self):
        old_date = (date.today() - timedelta(days=3)).isoformat()
        streak, continued = update_streak(old_date, 10)
        assert streak == 1
        assert not continued


# ---------------------------------------------------------------------------
# Badge checking
# ---------------------------------------------------------------------------

class TestBadges:
    def test_first_quiz_badge(self):
        new = check_badges(
            total_tests=1, current_streak=1, level=1, percent=70,
            languages_used=1, topics_used=1, all_fast=False, existing_badges=set(),
        )
        assert "first_quiz" in new

    def test_perfect_score_badge(self):
        new = check_badges(
            total_tests=5, current_streak=1, level=1, percent=100,
            languages_used=1, topics_used=1, all_fast=False, existing_badges={"first_quiz"},
        )
        assert "perfect_score" in new

    def test_streak_badges(self):
        new = check_badges(
            total_tests=10, current_streak=7, level=2, percent=80,
            languages_used=1, topics_used=3, all_fast=False, existing_badges={"first_quiz", "streak_3"},
        )
        assert "streak_7" in new
        assert "tests_10" in new
        assert "streak_3" not in new  # already had it

    def test_no_duplicates(self):
        new = check_badges(
            total_tests=1, current_streak=1, level=1, percent=100,
            languages_used=1, topics_used=1, all_fast=False,
            existing_badges={"first_quiz", "perfect_score"},
        )
        assert "first_quiz" not in new
        assert "perfect_score" not in new

    def test_speed_demon(self):
        new = check_badges(
            total_tests=5, current_streak=1, level=1, percent=80,
            languages_used=1, topics_used=1, all_fast=True, existing_badges={"first_quiz"},
        )
        assert "speed_demon" in new

    def test_polyglot(self):
        new = check_badges(
            total_tests=5, current_streak=1, level=1, percent=70,
            languages_used=2, topics_used=3, all_fast=False, existing_badges={"first_quiz"},
        )
        assert "polyglot" in new

    def test_explorer(self):
        new = check_badges(
            total_tests=5, current_streak=1, level=1, percent=70,
            languages_used=1, topics_used=5, all_fast=False, existing_badges={"first_quiz"},
        )
        assert "explorer" in new


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------

class TestThemes:
    def test_all_themes_exist(self):
        expected = {"neutral", "minecraft", "ninjago", "space", "superhero"}
        assert set(THEMES.keys()) == expected

    def test_all_themes_have_required_keys(self):
        required_keys = [
            "display_name", "xp_name", "xp_emoji", "streak_emoji", "levels",
            "correct_msg", "wrong_msg", "perfect_msg", "good_msg", "ok_msg",
            "weak_msg", "xp_earn", "streak_msg", "level_msg", "badge_msg",
        ]
        for theme_key, theme in THEMES.items():
            for key in required_keys:
                assert key in theme, f"Theme '{theme_key}' missing key '{key}'"

    def test_result_comment_perfect(self):
        comment = get_result_comment("minecraft", 95)
        assert comment == THEMES["minecraft"]["perfect_msg"]

    def test_result_comment_good(self):
        comment = get_result_comment("neutral", 75)
        assert comment == THEMES["neutral"]["good_msg"]

    def test_result_comment_ok(self):
        comment = get_result_comment("space", 55)
        assert comment == THEMES["space"]["ok_msg"]

    def test_result_comment_weak(self):
        comment = get_result_comment("superhero", 30)
        assert comment == THEMES["superhero"]["weak_msg"]

    def test_get_theme_fallback(self):
        theme = get_theme("nonexistent")
        assert theme == THEMES["neutral"]

    def test_format_results_text(self):
        text = format_results_text(
            theme_key="minecraft",
            language="English",
            topic="Present Simple",
            correct=7, total=10, percent=70,
            xp_earned=70, streak_days=3,
            level=2, xp_total=250,
            new_badges=["tests_10"],
        )
        assert "English" in text
        assert "Present Simple" in text
        assert "70" in text
        assert "250" in text

    def test_format_gamification_header(self):
        header = format_gamification_header(
            theme_key="neutral", streak=5, level=3, xp_total=400, badge_count=3,
        )
        assert "5" in header
        assert "400" in header
        assert "3" in header


# ---------------------------------------------------------------------------
# Badges config
# ---------------------------------------------------------------------------

class TestBadgesConfig:
    def test_all_badges_have_emoji_and_name(self):
        for key, (emoji, name) in BADGES.items():
            assert emoji, f"Badge '{key}' has empty emoji"
            assert name, f"Badge '{key}' has empty name"

    def test_badge_count(self):
        assert len(BADGES) == 11
