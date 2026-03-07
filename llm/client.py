"""OpenAI-compatible LLM client with bridge -> direct fallback."""
import logging
from typing import Optional

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)
_last_llm_error: str | None = None


def _normalize_base_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return url.rstrip("/")


def get_last_llm_error() -> str | None:
    """Return the last LLM transport/config error captured by chat_completion."""
    return _last_llm_error


def _iter_llm_targets() -> list[tuple[str, str, str]]:
    """Return request targets in priority order: bridge first, then direct."""
    targets: list[tuple[str, str, str]] = []
    bridge_url = _normalize_base_url(settings.LLM_BRIDGE_URL)
    direct_url = _normalize_base_url(settings.LLM_BASE_URL)
    api_key = settings.LLM_API_KEY or "not-needed"

    if bridge_url:
        targets.append((bridge_url, api_key, "bridge"))

    if direct_url and direct_url != bridge_url:
        targets.append((direct_url, api_key, "direct"))

    return targets


async def _request_chat_completion(
    base_url: str,
    api_key: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=settings.LLM_REQUEST_TIMEOUT,
    )
    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


async def chat_completion(prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str | None:
    """Send prompt to configured LLM targets. Bridge is attempted before direct endpoint."""
    global _last_llm_error
    targets = _iter_llm_targets()
    if not targets:
        logger.error("No LLM endpoints configured (LLM_BRIDGE_URL/LLM_BASE_URL are empty)")
        _last_llm_error = "No LLM endpoints configured"
        return None

    for base_url, api_key, label in targets:
        try:
            result = await _request_chat_completion(
                base_url=base_url,
                api_key=api_key,
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if result:
                _last_llm_error = None
                return result
            logger.warning("LLM %s endpoint returned empty response", label)
            _last_llm_error = f"{label} endpoint returned empty response"
        except Exception as e:
            _last_llm_error = f"{label} endpoint failed: {e}"
            logger.warning(
                "LLM request failed via %s endpoint (url=%s, model=%s, prompt_len=%d): %s",
                label,
                base_url,
                settings.LLM_MODEL,
                len(prompt),
                e,
            )

    logger.error("All LLM endpoints failed (model=%s, prompt_len=%d)", settings.LLM_MODEL, len(prompt))
    if _last_llm_error is None:
        _last_llm_error = "All LLM endpoints failed"
    return None
