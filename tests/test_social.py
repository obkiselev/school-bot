"""Tests for social features helper logic."""
from datetime import date

import pytest

from handlers.social import _week_bounds, _format_shared_result_text, _build_admin_social_report


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


@pytest.mark.asyncio
async def test_build_admin_social_report(monkeypatch):
    async def fake_xp(limit=10):
        return [
            {"display_name": "Ivan", "xp_total": 1200, "level": 4, "current_streak": 7},
        ]

    async def fake_weekly(start, end, limit=10):
        return [
            {"display_name": "Petr", "tests_count": 5, "avg_score": 82.5},
        ]

    monkeypatch.setattr("handlers.social.get_xp_leaderboard", fake_xp)
    monkeypatch.setattr("handlers.social.get_weekly_tests_leaderboard", fake_weekly)

    text = await _build_admin_social_report()
    assert "Social Admin Report" in text
    assert "Ivan" in text
    assert "Petr" in text
