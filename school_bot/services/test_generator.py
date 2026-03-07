"""Test generation via LLM."""
import logging

from config import settings
from llm.client import chat_completion, get_last_llm_error
from llm.prompts import build_test_prompt
from llm.parser import parse_questions
from services.fallback_test_generator import generate_fallback_test

logger = logging.getLogger(__name__)


def _mark_source(questions: list[dict], source: str, reason: str | None = None) -> list[dict]:
    """Attach generation source marker to each question."""
    marked: list[dict] = []
    for q in questions:
        item = dict(q)
        item["_source"] = source
        if reason:
            item["_source_reason"] = reason
        marked.append(item)
    return marked


async def generate_test(language: str, topic: str, count: int, user_id: int | None = None, level: str = "A2") -> list[dict] | None:
    """Generate a test with the given parameters. Returns list of questions or None."""
    previous_questions: list[str] = []
    if user_id:
        try:
            from database.crud import get_recent_questions
            previous_questions = await get_recent_questions(user_id, language, topic)
        except Exception:
            logger.warning("Could not fetch question history, proceeding without it")

    prompt = build_test_prompt(language, topic, count, level=level, previous_questions=previous_questions or None)

    # First attempt
    raw = await chat_completion(prompt)
    questions = parse_questions(raw) if raw else None

    if questions and len(questions) >= count:
        return _mark_source(questions[:count], "llm")

    # Retry once with a stricter prompt
    logger.info("First attempt didn't produce enough questions, retrying...")
    retry_prompt = prompt + "\n\nIMPORTANT: Output ONLY a valid JSON array. No markdown, no extra text."
    raw = await chat_completion(retry_prompt)
    questions = parse_questions(raw) if raw else None

    if questions:
        return _mark_source(questions[:count], "llm")

    if settings.LLM_FALLBACK_ENABLED:
        reason = get_last_llm_error() or "LLM unavailable"
        logger.warning("LLM unavailable, switching to template fallback quiz: %s", reason)
        return _mark_source(generate_fallback_test(language, topic, count, level=level), "fallback", reason=reason)

    logger.error("Failed to generate test after 2 attempts")
    return None
