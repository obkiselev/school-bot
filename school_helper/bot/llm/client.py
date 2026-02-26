import logging
from openai import AsyncOpenAI

from bot.config import LLM_BASE_URL, LLM_MODEL

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key="not-needed")


async def chat_completion(prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str | None:
    """Send a prompt to LM Studio and return the response text."""
    try:
        response = await _client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        return None
