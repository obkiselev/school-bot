"""Runtime health checks for admin monitoring."""
import asyncio
from typing import Any

import aiohttp

from config import settings
from core.database import get_db
from llm.client import _iter_llm_targets


async def _check_db() -> tuple[bool, str]:
    try:
        db = get_db()
        row = await db.fetchone("SELECT 1 as ok")
        if row and int(row["ok"]) == 1:
            return True, "ok"
        return False, "unexpected result"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def _check_llm_target(base_url: str, api_key: str, label: str) -> tuple[bool, str]:
    url = base_url.rstrip("/") + "/models"
    headers = {}
    if api_key and api_key != "not-needed":
        headers["Authorization"] = f"Bearer {api_key}"

    timeout = aiohttp.ClientTimeout(total=min(max(settings.LLM_REQUEST_TIMEOUT, 5), 30))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if 200 <= resp.status < 300:
                    return True, f"{label}: HTTP {resp.status}"
                return False, f"{label}: HTTP {resp.status}"
    except Exception as e:
        return False, f"{label}: {type(e).__name__}: {e}"


async def collect_health_status() -> dict[str, Any]:
    """Collect current runtime health status."""
    db_ok, db_msg = await _check_db()

    llm_targets = _iter_llm_targets()
    llm_results: list[tuple[bool, str]] = []
    if llm_targets:
        tasks = [
            _check_llm_target(base_url, api_key, label)
            for base_url, api_key, label in llm_targets
        ]
        llm_results = await asyncio.gather(*tasks)

    llm_ok = any(ok for ok, _ in llm_results) if llm_results else False

    return {
        "db_ok": db_ok,
        "db_message": db_msg,
        "llm_targets": llm_targets,
        "llm_results": llm_results,
        "llm_ok": llm_ok,
    }


def format_health_message(status: dict[str, Any]) -> str:
    """Render human-friendly health report for Telegram."""
    db_mark = "✅" if status["db_ok"] else "❌"
    llm_mark = "✅" if status["llm_ok"] else "❌"

    lines = [
        "🩺 Health check",
        "",
        f"{db_mark} БД: {status['db_message']}",
    ]

    targets = status.get("llm_targets", [])
    if not targets:
        lines.append("ℹ️ LLM: endpoint'ы не настроены (fallback-режим)")
    else:
        result_map: dict[str, tuple[bool, str]] = {}
        for ok, msg in status.get("llm_results", []):
            label = msg.split(":", 1)[0].strip().lower()
            result_map[label] = (ok, msg)

        bridge_ok = result_map.get("bridge", (False, ""))[0]
        lines.append(f"{llm_mark} LLM targets:")
        for ok, msg in status.get("llm_results", []):
            label = msg.split(":", 1)[0].strip().lower()

            # In tunnel mode bridge is primary; direct can be unavailable on VPS by design.
            if label == "direct" and bridge_ok and not ok:
                lines.append(f"  ℹ️ {msg} (ожидаемо: используется bridge)")
                continue

            mark = "✅" if ok else "❌"
            lines.append(f"  {mark} {msg}")

    return "\n".join(lines)
