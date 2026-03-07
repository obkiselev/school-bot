"""Tests for template fallback quiz generation."""
import importlib
import pytest


def test_generate_fallback_questions_count_and_types():
    from services.quiz_fallback import generate_fallback_questions

    questions = generate_fallback_questions("English", "School", 8)

    assert len(questions) == 8
    assert questions[0]["type"] == "multiple_choice"
    assert questions[1]["type"] == "fill_blank"
    assert questions[2]["type"] == "translation"
    assert questions[3]["type"] == "true_false"

    for q in questions:
        assert q.get("question")
        assert q.get("correct")
        assert q.get("explanation")


@pytest.mark.asyncio
async def test_generate_test_uses_template_fallback_when_llm_unavailable(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    test_generator = importlib.import_module("services.test_generator")

    async def _fake_chat_completion(*args, **kwargs):
        return None

    def _fake_parse_questions(*args, **kwargs):
        return None

    monkeypatch.setattr(test_generator, "chat_completion", _fake_chat_completion)
    monkeypatch.setattr(test_generator, "parse_questions", _fake_parse_questions)
    monkeypatch.setattr(test_generator.settings, "QUIZ_TEMPLATE_FALLBACK_ENABLED", True)

    questions = await test_generator.generate_test("English", "School", 5, user_id=None, level="A2")

    assert questions is not None
    assert len(questions) == 5
    assert all("type" in q for q in questions)
