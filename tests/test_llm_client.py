"""Tests for llm/client.py target selection and fallback order."""
import pytest

from llm import client
from config import settings


def test_iter_targets_bridge_then_direct(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BRIDGE_URL", "https://bridge.example/v1")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setattr(settings, "LLM_API_KEY", "secret-token")

    targets = client._iter_llm_targets()
    assert targets == [
        ("https://bridge.example/v1", "secret-token", "bridge"),
        ("http://localhost:1234/v1", "secret-token", "direct"),
    ]


@pytest.mark.asyncio
async def test_chat_completion_tries_direct_after_bridge_failure(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BRIDGE_URL", "https://bridge.example/v1")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setattr(settings, "LLM_API_KEY", "secret-token")

    calls: list[str] = []

    async def fake_request(base_url, api_key, prompt, temperature, max_tokens):
        calls.append(base_url)
        if "bridge.example" in base_url:
            raise RuntimeError("bridge offline")
        return "ok-from-direct"

    monkeypatch.setattr(client, "_request_chat_completion", fake_request)

    result = await client.chat_completion("hello")
    assert result == "ok-from-direct"
    assert calls == [
        "https://bridge.example/v1",
        "http://localhost:1234/v1",
    ]
