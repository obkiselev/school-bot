"""OpenAI-compatible LLM client with bridge -> direct fallback."""
import io
import logging
from typing import Optional

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)
_last_llm_error: str | None = None
_last_stt_error: str | None = None


def _normalize_base_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return url.rstrip("/")


def get_last_llm_error() -> str | None:
    """Return the last LLM transport/config error captured by chat_completion."""
    return _last_llm_error


def get_last_stt_error() -> str | None:
    """Return the last STT transport/config error captured by transcribe_audio_bytes."""
    return _last_stt_error


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


def _build_audio_file_object(data: bytes, filename: str) -> io.BytesIO:
    file_obj = io.BytesIO(data)
    file_obj.name = filename
    return file_obj


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

    errors: list[str] = []
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
            msg = f"{label} endpoint returned empty response"
            errors.append(msg)
            _last_llm_error = msg
        except Exception as e:
            msg = f"{label} endpoint failed: {e}"
            errors.append(msg)
            _last_llm_error = msg
            logger.warning(
                "LLM request failed via %s endpoint (url=%s, model=%s, prompt_len=%d): %s",
                label,
                base_url,
                settings.LLM_MODEL,
                len(prompt),
                e,
            )

    logger.error("All LLM endpoints failed (model=%s, prompt_len=%d)", settings.LLM_MODEL, len(prompt))
    if errors:
        _last_llm_error = " | ".join(errors)
    elif _last_llm_error is None:
        _last_llm_error = "All LLM endpoints failed"
    return None


async def _request_audio_transcription(
    base_url: str,
    api_key: str,
    audio_bytes: bytes,
    filename: str,
) -> str:
    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=settings.LLM_REQUEST_TIMEOUT,
    )
    transcription = await client.audio.transcriptions.create(
        model=settings.STT_MODEL,
        file=_build_audio_file_object(audio_bytes, filename),
        language=settings.STT_LANGUAGE,
    )
    if hasattr(transcription, "text"):
        return (transcription.text or "").strip()
    if isinstance(transcription, dict):
        return str(transcription.get("text") or "").strip()
    return str(transcription).strip()


async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "voice.ogg") -> str | None:
    """Transcribe voice/audio bytes via OpenAI-compatible Whisper endpoint(s)."""
    global _last_stt_error

    if not settings.STT_ENABLED:
        _last_stt_error = "STT disabled by configuration"
        return None

    if not audio_bytes:
        _last_stt_error = "Empty audio payload"
        return None

    targets = _iter_llm_targets()
    if not targets:
        _last_stt_error = "No STT endpoints configured"
        logger.error("No STT endpoints configured (LLM_BRIDGE_URL/LLM_BASE_URL are empty)")
        return None

    for base_url, api_key, label in targets:
        try:
            text = await _request_audio_transcription(base_url, api_key, audio_bytes, filename)
            if text:
                _last_stt_error = None
                return text
            _last_stt_error = f"{label} endpoint returned empty transcription"
            logger.warning("STT %s endpoint returned empty transcription", label)
        except Exception as e:
            _last_stt_error = f"{label} endpoint failed: {e}"
            logger.warning("STT request failed via %s endpoint (url=%s): %s", label, base_url, e)

    if _last_stt_error is None:
        _last_stt_error = "All STT endpoints failed"
    logger.error("All STT endpoints failed (model=%s, bytes=%d)", settings.STT_MODEL, len(audio_bytes))
    return None
