"""Tests for template fallback in services/test_generator.py."""
import pytest

from config import settings
from services import test_generator


@pytest.mark.asyncio
async def test_generate_test_uses_fallback_when_llm_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "LLM_FALLBACK_ENABLED", True)

    async def always_none(*args, **kwargs):
        return None

    monkeypatch.setattr(test_generator, "chat_completion", always_none)

    questions = await test_generator.generate_test(
        language="English",
        topic="Present Simple",
        count=5,
        user_id=None,
        level="A2",
    )

    assert questions is not None
    assert len(questions) == 5
    assert all(q.get("type") for q in questions)
    assert all(q.get("question", "").startswith("[Fallback | A2 | Present Simple]") for q in questions)


@pytest.mark.asyncio
async def test_generate_test_returns_none_when_fallback_disabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_FALLBACK_ENABLED", False)

    async def always_none(*args, **kwargs):
        return None

    monkeypatch.setattr(test_generator, "chat_completion", always_none)

    questions = await test_generator.generate_test(
        language="English",
        topic="Present Simple",
        count=5,
        user_id=None,
        level="A2",
    )

    assert questions is None
