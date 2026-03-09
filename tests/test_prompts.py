"""Tests for prompt building."""

from llm.prompts import build_test_prompt


def test_math_prompt_mentions_only_math_subject():
    prompt = build_test_prompt("Mathematics", "Линейные уравнения", 5, level="School")
    assert "strictly for Mathematics" in prompt
    assert "В каком году началась Отечественная война" not in prompt
    assert "Какой орган перекачивает кровь" not in prompt


def test_history_prompt_mentions_only_history_subject():
    prompt = build_test_prompt("History", "История России XIX века", 5, level="School")
    assert "strictly for History" in prompt
    assert "периметр квадрата" not in prompt
    assert "фотосинтез" not in prompt
