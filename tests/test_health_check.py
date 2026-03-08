import pytest

from services import health_check


@pytest.mark.asyncio
async def test_collect_health_no_llm_targets(monkeypatch):
    async def fake_db():
        return True, "ok"

    monkeypatch.setattr(health_check, "_check_db", fake_db)
    monkeypatch.setattr(health_check, "_iter_llm_targets", lambda: [])

    status = await health_check.collect_health_status()
    assert status["db_ok"] is True
    assert status["llm_targets"] == []
    assert status["llm_ok"] is False


@pytest.mark.asyncio
async def test_collect_health_llm_success(monkeypatch):
    async def fake_db():
        return True, "ok"

    async def fake_target(base_url, api_key, label):
        assert label == "bridge"
        return True, "bridge: HTTP 200"

    monkeypatch.setattr(health_check, "_check_db", fake_db)
    monkeypatch.setattr(
        health_check,
        "_iter_llm_targets",
        lambda: [("http://127.0.0.1:8787/v1", "token", "bridge")],
    )
    monkeypatch.setattr(health_check, "_check_llm_target", fake_target)

    status = await health_check.collect_health_status()
    assert status["llm_ok"] is True
    assert status["llm_results"] == [(True, "bridge: HTTP 200")]


def test_format_health_message():
    text = health_check.format_health_message(
        {
            "db_ok": True,
            "db_message": "ok",
            "llm_targets": [("http://127.0.0.1:8787/v1", "token", "bridge")],
            "llm_results": [(False, "bridge: HTTP 401")],
            "llm_ok": False,
        }
    )
    assert "🩺 Health check" in text
    assert "✅ БД: ok" in text
    assert "❌ LLM targets:" in text
    assert "❌ bridge: HTTP 401" in text
