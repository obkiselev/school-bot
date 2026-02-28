"""Общие фикстуры для тестов школьного бота."""
import pytest
from datetime import date
from mesh_api.models import Lesson


@pytest.fixture
def sample_lessons():
    """Список уроков со всеми заполненными полями."""
    return [
        Lesson(
            number=1,
            subject="Математика",
            time_start="08:30",
            time_end="09:15",
            teacher="Иванова А.П.",
            room="301",
        ),
        Lesson(
            number=2,
            subject="Русский язык",
            time_start="09:25",
            time_end="10:10",
            teacher="Петрова М.И.",
            room="205",
        ),
    ]


@pytest.fixture
def sample_user():
    """Зарегистрированный пользователь из БД."""
    return {
        "user_id": 12345,
        "mesh_login": "test_login",
        "mesh_password": "test_pass",
        "mesh_token": "valid_token",
        "token_expires_at": "2026-03-01T12:00:00",
        "is_active": 1,
    }


@pytest.fixture
def sample_children():
    """Один ребёнок, привязанный к пользователю."""
    return [
        {
            "child_id": 1,
            "user_id": 12345,
            "student_id": 100,
            "first_name": "Иван",
            "last_name": "Иванов",
            "class_name": "9А",
            "is_active": 1,
        }
    ]


@pytest.fixture
def multiple_children():
    """Несколько детей, привязанных к пользователю."""
    return [
        {
            "child_id": 1,
            "user_id": 12345,
            "student_id": 100,
            "first_name": "Иван",
            "last_name": "Иванов",
            "class_name": "9А",
            "is_active": 1,
        },
        {
            "child_id": 2,
            "user_id": 12345,
            "student_id": 200,
            "first_name": "Мария",
            "last_name": "Иванова",
            "class_name": "5Б",
            "is_active": 1,
        },
    ]


@pytest.fixture
def today():
    """Фиксированная дата для тестов (среда)."""
    return date(2026, 2, 25)  # Среда
