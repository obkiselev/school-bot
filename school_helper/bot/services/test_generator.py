import logging

from bot.llm.client import chat_completion
from bot.llm.prompts import build_test_prompt
from bot.llm.parser import parse_questions

logger = logging.getLogger(__name__)


async def generate_test(language: str, topic: str, count: int) -> list[dict] | None:
    """Generate a test with the given parameters. Returns list of questions or None."""
    prompt = build_test_prompt(language, topic, count)

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

    logger.error("Failed to generate test after 2 attempts")
    return None
