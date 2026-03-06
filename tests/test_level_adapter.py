"""Tests for services/level_adapter.py -- grade extraction and CEFR mapping."""
import pytest
from unittest.mock import AsyncMock, patch

from services.level_adapter import (
    extract_grade,
    grade_to_language_level,
    get_user_level,
    AVAILABLE_LEVELS,
    DEFAULT_LEVEL,
)


class TestExtractGrade:
    def test_latin_letter(self):
        assert extract_grade("5A") == 5

    def test_cyrillic_letter(self):
        assert extract_grade("11\u0411") == 11

    def test_single_digit(self):
        assert extract_grade("3\u0412") == 3

    def test_two_digits(self):
        assert extract_grade("10\u0410") == 10

    def test_empty_string(self):
        assert extract_grade("") is None

    def test_none_input(self):
        assert extract_grade(None) is None

    def test_no_digits(self):
        assert extract_grade("ABC") is None

    def test_with_spaces(self):
        assert extract_grade("5 \u0410 \u043a\u043b\u0430\u0441\u0441") == 5


class TestGradeToLevel:
    def test_english_grade_3(self):
        assert grade_to_language_level(3, "English") == "A1"

    def test_english_grade_5(self):
        assert grade_to_language_level(5, "English") == "A2"

    def test_english_grade_7(self):
        assert grade_to_language_level(7, "English") == "B1"

    def test_english_grade_9(self):
        assert grade_to_language_level(9, "English") == "B2"

    def test_english_grade_11(self):
        assert grade_to_language_level(11, "English") == "B2"

    def test_spanish_grade_5(self):
        assert grade_to_language_level(5, "Spanish") == "A1"

    def test_spanish_grade_7(self):
        assert grade_to_language_level(7, "Spanish") == "A1-A2"

    def test_spanish_grade_10(self):
        assert grade_to_language_level(10, "Spanish") == "A2"

    def test_unknown_language_fallback(self):
        assert grade_to_language_level(5, "French") == DEFAULT_LEVEL

    def test_grade_zero_fallback(self):
        assert grade_to_language_level(0, "English") == DEFAULT_LEVEL

    def test_grade_beyond_range(self):
        assert grade_to_language_level(12, "English") == DEFAULT_LEVEL


class TestAvailableLevels:
    def test_english_has_c1(self):
        assert "C1" in AVAILABLE_LEVELS["English"]

    def test_spanish_levels(self):
        assert AVAILABLE_LEVELS["Spanish"] == ["A1", "A1-A2", "A2", "B1"]


@pytest.mark.asyncio
class TestGetUserLevel:
    @patch("database.crud.get_user_children", new_callable=AsyncMock)
    @patch("database.crud.get_user_role", new_callable=AsyncMock)
    async def test_student_with_class(self, mock_role, mock_children):
        mock_role.return_value = "student"
        mock_children.return_value = [{"class_name": "5A"}]
        level = await get_user_level(123, "English")
        assert level == "A2"

    @patch("database.crud.get_user_children", new_callable=AsyncMock)
    @patch("database.crud.get_user_role", new_callable=AsyncMock)
    async def test_student_no_children(self, mock_role, mock_children):
        mock_role.return_value = "student"
        mock_children.return_value = []
        level = await get_user_level(123, "English")
        assert level == DEFAULT_LEVEL

    @patch("database.crud.get_user_role", new_callable=AsyncMock)
    async def test_parent_returns_none(self, mock_role):
        mock_role.return_value = "parent"
        level = await get_user_level(123, "English")
        assert level is None

    @patch("database.crud.get_user_role", new_callable=AsyncMock)
    async def test_admin_returns_none(self, mock_role):
        mock_role.return_value = "admin"
        level = await get_user_level(123, "English")
        assert level is None

    @patch("database.crud.get_user_children", new_callable=AsyncMock)
    @patch("database.crud.get_user_role", new_callable=AsyncMock)
    async def test_student_no_class_name(self, mock_role, mock_children):
        mock_role.return_value = "student"
        mock_children.return_value = [{"class_name": None}]
        level = await get_user_level(123, "English")
        assert level == DEFAULT_LEVEL

    @patch("database.crud.get_user_children", new_callable=AsyncMock)
    @patch("database.crud.get_user_role", new_callable=AsyncMock)
    async def test_student_grade_9_spanish(self, mock_role, mock_children):
        mock_role.return_value = "student"
        mock_children.return_value = [{"class_name": "9\u0410"}]
        level = await get_user_level(123, "Spanish")
        assert level == "A2"
