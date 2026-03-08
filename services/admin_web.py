"""Admin web panel and group broadcasts (v1.6.0)."""
from __future__ import annotations

import asyncio
import html
import logging
import secrets
from typing import Optional, List

from aiohttp import web
from aiogram import Bot

from config import settings
from database.crud import (
    get_admin_broadcast_history,
    create_admin_broadcast,
    finish_admin_broadcast,
    get_admin_daily_tests,
    get_admin_dashboard_stats,
    get_broadcast_target_user_ids,
    log_admin_broadcast_recipient,
    normalize_broadcast_roles,
)

logger = logging.getLogger(__name__)


def _extract_token(request: web.Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return (request.query.get("token") or "").strip()


def _check_auth(request: web.Request) -> bool:
    expected = (settings.ADMIN_WEB_TOKEN or "").strip()
    if not expected:
        return False
    return secrets.compare_digest(_extract_token(request), expected)


def _sanitize_broadcast_text(text: str) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) > 4000:
        cleaned = cleaned[:4000]
    return cleaned


def _render_panel_html(token: str) -> str:
    safe_token = html.escape(token)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>School Bot Admin</title>
  <style>
    :root {{
      --bg1: #f8f2e9;
      --bg2: #e9f6ff;
      --card: #ffffff;
      --ink: #132238;
      --muted: #4f647f;
      --accent: #0b6bcb;
      --ok: #217a36;
      --err: #b22d2d;
      --line: #d5deea;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at top left, var(--bg1), transparent 45%),
                  radial-gradient(circle at top right, var(--bg2), transparent 50%),
                  #f5f9ff;
    }}
    .wrap {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 24px 16px 36px;
    }}
    h1 {{
      margin: 0 0 16px;
      font-size: 28px;
      letter-spacing: 0.2px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      box-shadow: 0 4px 12px rgba(20, 40, 60, 0.05);
    }}
    .metric {{
      font-size: 24px;
      font-weight: 700;
      margin-top: 6px;
    }}
    .label {{
      color: var(--muted);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .panel {{
      display: grid;
      grid-template-columns: 1.3fr 1fr;
      gap: 14px;
    }}
    @media (max-width: 900px) {{
      .panel {{ grid-template-columns: 1fr; }}
    }}
    canvas {{
      width: 100%;
      height: 260px;
      background: #fbfdff;
      border-radius: 8px;
      border: 1px solid var(--line);
    }}
    textarea {{
      width: 100%;
      min-height: 120px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      font: inherit;
      box-sizing: border-box;
      resize: vertical;
    }}
    .row {{
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      margin: 10px 0;
    }}
    .btn {{
      border: 0;
      background: var(--accent);
      color: white;
      border-radius: 8px;
      padding: 9px 14px;
      cursor: pointer;
      font-weight: 600;
    }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    #result.ok {{ color: var(--ok); }}
    #result.err {{ color: var(--err); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      padding: 8px 6px;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      font-size: 11px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>School Bot Admin</h1>
    <div id="cards" class="grid"></div>
    <div class="panel">
      <div class="card">
        <div class="label">Тесты за 14 дней</div>
        <canvas id="chart" width="720" height="260"></canvas>
        <div class="muted">Синяя линия: количество тестов, красная: средний балл %.</div>
      </div>
      <div class="card">
        <div class="label">Групповая рассылка</div>
        <textarea id="message" placeholder="Текст сообщения..."></textarea>
        <div class="row">
          <label><input id="r-student" type="checkbox" checked /> ученики</label>
          <label><input id="r-parent" type="checkbox" checked /> родители</label>
          <label><input id="r-admin" type="checkbox" /> админы</label>
          <label><input id="dry-run" type="checkbox" /> dry-run</label>
        </div>
        <div class="row">
          <button id="send" class="btn">Отправить</button>
          <span id="result" class="muted"></span>
        </div>
      </div>
    </div>
    <div class="card" style="margin-top:14px">
      <div class="label">История рассылок</div>
      <div class="muted" style="margin:6px 0 10px">Последние 30 запусков групповой рассылки.</div>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Статус</th>
            <th>Роли</th>
            <th>Итог</th>
            <th>Создано</th>
            <th>Текст</th>
          </tr>
        </thead>
        <tbody id="broadcast-history"></tbody>
      </table>
    </div>
  </div>
  <script>
    const token = "{safe_token}";

    async function apiGet(path) {{
      const r = await fetch(`${{path}}?token=${{encodeURIComponent(token)}}`);
      if (!r.ok) throw new Error(`HTTP ${{r.status}}`);
      return r.json();
    }}

    async function loadCards() {{
      const data = await apiGet('/admin/api/stats');
      const cards = [
        ['Пользователи', data.users_total],
        ['Активные 7д', data.active_users_7d],
        ['Ученики', data.users_students],
        ['Родители', data.users_parents],
        ['Админы', data.users_admins],
        ['Тестов всего', data.tests_total],
        ['Тестов 7д', data.tests_7d],
        ['Средний балл 30д', data.avg_score_30d],
      ];
      document.getElementById('cards').innerHTML = cards
        .map(([label, value]) => `<div class="card"><div class="label">${{label}}</div><div class="metric">${{value}}</div></div>`)
        .join('');
    }}

    function drawChart(points) {{
      const canvas = document.getElementById('chart');
      const ctx = canvas.getContext('2d');
      const w = canvas.width, h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#f8fbff';
      ctx.fillRect(0, 0, w, h);

      if (!points.length) {{
        ctx.fillStyle = '#556b85';
        ctx.font = '16px Segoe UI';
        ctx.fillText('Нет данных за выбранный период', 20, 30);
        return;
      }}

      const pad = 32;
      const maxTests = Math.max(1, ...points.map(p => p.tests_count));
      const maxScore = 100;
      const stepX = points.length > 1 ? (w - pad * 2) / (points.length - 1) : 0;
      const yTests = v => h - pad - (v / maxTests) * (h - pad * 2);
      const yScore = v => h - pad - (v / maxScore) * (h - pad * 2);

      ctx.strokeStyle = '#d1ddeb';
      ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i++) {{
        const y = pad + ((h - pad * 2) / 4) * i;
        ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - pad, y); ctx.stroke();
      }}

      ctx.strokeStyle = '#0b6bcb';
      ctx.lineWidth = 2;
      ctx.beginPath();
      points.forEach((p, i) => {{
        const x = pad + i * stepX;
        const y = yTests(p.tests_count);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }});
      ctx.stroke();

      ctx.strokeStyle = '#c13b2f';
      ctx.lineWidth = 2;
      ctx.beginPath();
      points.forEach((p, i) => {{
        const x = pad + i * stepX;
        const y = yScore(p.avg_score);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }});
      ctx.stroke();
    }}

    async function loadChart() {{
      const rows = await apiGet('/admin/api/tests-daily');
      drawChart(rows);
    }}

    async function sendBroadcast() {{
      const roles = [];
      if (document.getElementById('r-student').checked) roles.push('student');
      if (document.getElementById('r-parent').checked) roles.push('parent');
      if (document.getElementById('r-admin').checked) roles.push('admin');

      const payload = {{
        text: document.getElementById('message').value,
        roles,
        dry_run: document.getElementById('dry-run').checked
      }};

      const resultNode = document.getElementById('result');
      resultNode.className = 'muted';
      resultNode.textContent = 'Отправка...';

      try {{
        const r = await fetch('/admin/api/broadcast?token=' + encodeURIComponent(token), {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || `HTTP ${{r.status}}`);
        resultNode.className = 'ok';
        resultNode.textContent = `run #${{data.broadcast_id}}: targets=${{data.total_targets}}, sent=${{data.sent_count}}, failed=${{data.failed_count}}`;
        loadBroadcastHistory();
      }} catch (e) {{
        resultNode.className = 'err';
        resultNode.textContent = e.message;
      }}
    }}

    async function loadBroadcastHistory() {{
      const rows = await apiGet('/admin/api/broadcast-history');
      const node = document.getElementById('broadcast-history');
      const esc = (v) => String(v ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
      if (!rows.length) {{
        node.innerHTML = '<tr><td colspan=\"6\" class=\"muted\">Пока нет запусков.</td></tr>';
        return;
      }}
      node.innerHTML = rows.map((r) => {{
        const roles = esc((r.target_roles || []).join(', ') || '-');
        const total = esc(`targets=${{r.total_targets}}, sent=${{r.sent_count}}, failed=${{r.failed_count}}`);
        return `<tr>
          <td>${{esc(r.id)}}</td>
          <td>${{esc(r.status)}}</td>
          <td>${{roles}}</td>
          <td>${{total}}</td>
          <td>${{esc(r.created_at || '-')}}</td>
          <td>${{esc(r.message_preview || '-')}}</td>
        </tr>`;
      }}).join('');
    }}

    document.getElementById('send').addEventListener('click', sendBroadcast);
    loadCards();
    loadChart();
    loadBroadcastHistory();
  </script>
</body>
</html>
"""


class AdminWebServer:
    """Embedded aiohttp admin panel."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.app = web.Application()
        self.app["bot"] = bot
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._configure_routes()

    def _configure_routes(self) -> None:
        self.app.add_routes(
            [
                web.get("/admin", self.handle_index),
                web.get("/admin/api/stats", self.handle_stats),
                web.get("/admin/api/tests-daily", self.handle_tests_daily),
                web.get("/admin/api/broadcast-history", self.handle_broadcast_history),
                web.post("/admin/api/broadcast", self.handle_broadcast),
            ]
        )

    async def start(self) -> None:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(
            self.runner,
            host=settings.ADMIN_WEB_HOST,
            port=settings.ADMIN_WEB_PORT,
        )
        await self.site.start()
        logger.info(
            "Admin web started on http://%s:%s/admin",
            settings.ADMIN_WEB_HOST,
            settings.ADMIN_WEB_PORT,
        )

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
            self.site = None
            logger.info("Admin web stopped")

    async def handle_index(self, request: web.Request) -> web.Response:
        if not _check_auth(request):
            return web.Response(text="Unauthorized. Pass ?token=...", status=401)
        return web.Response(
            text=_render_panel_html(_extract_token(request)),
            content_type="text/html",
        )

    async def handle_stats(self, request: web.Request) -> web.Response:
        if not _check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response(await get_admin_dashboard_stats())

    async def handle_tests_daily(self, request: web.Request) -> web.Response:
        if not _check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        days_raw = request.query.get("days", "14")
        try:
            days = int(days_raw)
        except ValueError:
            days = 14
        return web.json_response(await get_admin_daily_tests(days=days))

    async def handle_broadcast_history(self, request: web.Request) -> web.Response:
        if not _check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response(await get_admin_broadcast_history(limit=30))

    async def handle_broadcast(self, request: web.Request) -> web.Response:
        if not _check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)

        payload = await request.json()
        text = _sanitize_broadcast_text(payload.get("text", ""))
        roles = normalize_broadcast_roles(payload.get("roles"))
        dry_run = bool(payload.get("dry_run", False))

        if not text:
            return web.json_response({"error": "empty text"}, status=400)

        targets = await get_broadcast_target_user_ids(roles)
        status = "dry_run" if dry_run else "running"
        broadcast_id = await create_admin_broadcast(
            initiated_by=settings.ADMIN_ID,
            message_text=text,
            roles=roles,
            total_targets=len(targets),
            status=status,
        )

        sent_count = 0
        failed_count = 0
        if dry_run:
            await finish_admin_broadcast(
                broadcast_id=broadcast_id,
                sent_count=0,
                failed_count=0,
                status="dry_run",
            )
            return web.json_response(
                {
                    "broadcast_id": broadcast_id,
                    "total_targets": len(targets),
                    "sent_count": 0,
                    "failed_count": 0,
                    "dry_run": True,
                }
            )

        for user_id in targets:
            try:
                await self.bot.send_message(user_id, text)
                sent_count += 1
                await log_admin_broadcast_recipient(
                    broadcast_id=broadcast_id,
                    user_id=user_id,
                    status="sent",
                )
            except Exception as exc:
                failed_count += 1
                await log_admin_broadcast_recipient(
                    broadcast_id=broadcast_id,
                    user_id=user_id,
                    status="failed",
                    error_text=str(exc)[:500],
                )
                logger.warning("Broadcast failed for user %s: %s", user_id, exc)
            await asyncio.sleep(0.04)

        await finish_admin_broadcast(
            broadcast_id=broadcast_id,
            sent_count=sent_count,
            failed_count=failed_count,
            status="completed",
        )
        return web.json_response(
            {
                "broadcast_id": broadcast_id,
                "total_targets": len(targets),
                "sent_count": sent_count,
                "failed_count": failed_count,
                "dry_run": False,
            }
        )


async def start_admin_web(bot: Bot) -> Optional[AdminWebServer]:
    """Start admin web panel if enabled in settings."""
    if not settings.ADMIN_WEB_ENABLED:
        return None
    if not (settings.ADMIN_WEB_TOKEN or "").strip():
        raise RuntimeError("ADMIN_WEB_ENABLED=true requires ADMIN_WEB_TOKEN")
    server = AdminWebServer(bot)
    await server.start()
    return server
