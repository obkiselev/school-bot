"""Tests for STT transcription fallback logic in llm/client.py."""
import pytest

from config import settings
from llm import client


def test_get_last_stt_error_accessor():
    assert client.get_last_stt_error() is None or isinstance(client.get_last_stt_error(), str)


@pytest.mark.asyncio
async def test_transcribe_audio_tries_direct_after_bridge_failure(monkeypatch):
    monkeypatch.setattr(settings, "STT_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_BRIDGE_URL", "https://bridge.example/v1")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setattr(settings, "LLM_API_KEY", "secret-token")

    calls: list[str] = []

    async def fake_request(base_url, api_key, audio_bytes, filename):
        calls.append(base_url)
        if "bridge.example" in base_url:
            raise RuntimeError("bridge offline")
        return "распознанный текст"

    monkeypatch.setattr(client, "_request_audio_transcription", fake_request)

    result = await client.transcribe_audio_bytes(b"fake-audio", filename="voice.ogg")
    assert result == "распознанный текст"
    assert calls == [
        "https://bridge.example/v1",
        "http://localhost:1234/v1",
    ]


@pytest.mark.asyncio
async def test_transcribe_audio_respects_disabled_flag(monkeypatch):
    monkeypatch.setattr(settings, "STT_ENABLED", False)
    result = await client.transcribe_audio_bytes(b"fake-audio")
    assert result is None
    assert "disabled" in (client.get_last_stt_error() or "").lower()
