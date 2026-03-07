"""Test generation via LLM."""
import logging

from config import settings
from llm.client import chat_completion
from llm.prompts import build_test_prompt
from llm.parser import parse_questions
from services.quiz_fallback import generate_fallback_questions

logger = logging.getLogger(__name__)


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
        return questions[:count]

    # Retry once with a stricter prompt
    logger.info("First attempt didn't produce enough questions, retrying...")
    retry_prompt = prompt + "\n\nIMPORTANT: Output ONLY a valid JSON array. No markdown, no extra text."
    raw = await chat_completion(retry_prompt)
    questions = parse_questions(raw) if raw else None

    if questions:
        return questions[:count]

    if settings.QUIZ_TEMPLATE_FALLBACK_ENABLED:
        logger.warning(
            "LLM unavailable for quiz generation (language=%s, topic=%s, level=%s); using template fallback",
            language,
            topic,
            level,
        )
        return generate_fallback_questions(language, topic, count)

    logger.error("Failed to generate test after 2 attempts")
    return None
