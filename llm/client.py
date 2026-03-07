"""OpenAI-compatible LLM client (LM Studio)."""
import logging
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


def _build_clients() -> list[tuple[str, AsyncOpenAI]]:
    mode = settings.LLM_CONNECT_MODE
    clients: list[tuple[str, AsyncOpenAI]] = []

    if mode in {"remote", "auto"} and settings.LLM_REMOTE_BASE_URL:
        clients.append((
            "remote",
            AsyncOpenAI(
                base_url=settings.LLM_REMOTE_BASE_URL,
                api_key=settings.LLM_REMOTE_API_KEY or "not-needed",
                timeout=settings.LLM_REQUEST_TIMEOUT,
            ),
        ))

    if mode in {"local", "auto"} and settings.LLM_BASE_URL:
        clients.append((
            "local",
            AsyncOpenAI(
                base_url=settings.LLM_BASE_URL,
                api_key="not-needed",
                timeout=settings.LLM_REQUEST_TIMEOUT,
            ),
        ))

    return clients


_clients = _build_clients()


async def chat_completion(prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str | None:
    """Send a prompt to configured LLM endpoint(s) and return response text."""
    if not _clients:
        logger.error("No LLM endpoints configured (LLM_CONNECT_MODE=%s)", settings.LLM_CONNECT_MODE)
        return None

    for endpoint_name, client in _clients:
        try:
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content:
                return content
            logger.warning("LLM response was empty from endpoint=%s", endpoint_name)
        except Exception as e:
            logger.warning(
                "LLM request failed via endpoint=%s (model=%s, prompt_len=%d): %s",
                endpoint_name,
                settings.LLM_MODEL,
                len(prompt),
                e,
            )

    logger.error("LLM request failed on all configured endpoints")
    return None
