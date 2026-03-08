"""Tests for social features helper logic."""
from datetime import date

from handlers.social import _week_bounds, _format_shared_result_text


def test_week_bounds_monday_to_sunday():
    monday = date(2026, 3, 2)  # Monday
    start, end = _week_bounds(monday)
    assert start.isoformat() == "2026-03-02"
    assert end.isoformat() == "2026-03-08"


def test_format_shared_result_text_contains_main_fields():
    text = _format_shared_result_text(
        {
            "sender_name": "Ivan",
            "language": "English",
            "topic": "Present Simple",
            "correct_answers": 8,
            "total_questions": 10,
            "score_percent": 80,
            "finished_at": "2026-03-08 12:00:00",
        }
    )
    assert "Ivan" in text
    assert "English" in text
    assert "Present Simple" in text
    assert "8/10" in text
