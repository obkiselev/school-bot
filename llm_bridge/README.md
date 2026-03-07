# LLM Bridge Service

Локальный сервис-прокси для LM Studio с проверкой `Authorization: Bearer ...`.

## Что делает

- Принимает OpenAI-совместимые запросы на `/v1/*`
- Проверяет Bearer-токен
- Проксирует запрос в локальный LM Studio (`http://127.0.0.1:1234`)

## Переменные окружения

- `LLM_BRIDGE_TOKEN` — обязательный секретный токен
- `LLM_UPSTREAM_BASE_URL` — upstream LM Studio (по умолчанию `http://127.0.0.1:1234`)
- `LLM_BRIDGE_HOST` — bind host (по умолчанию `127.0.0.1`)
- `LLM_BRIDGE_PORT` — bind port (по умолчанию `8787`)
- `LLM_BRIDGE_TIMEOUT` — timeout в секундах (по умолчанию `45`)
- `LLM_BRIDGE_LOG_LEVEL` — уровень логов (по умолчанию `INFO`)

## Запуск (PowerShell)

```powershell
cd d:\claude\school_bot
$env:LLM_BRIDGE_TOKEN = "your_strong_bridge_token"
$env:LLM_UPSTREAM_BASE_URL = "http://127.0.0.1:1234"
$env:LLM_BRIDGE_HOST = "127.0.0.1"
$env:LLM_BRIDGE_PORT = "8787"
python -m llm_bridge.server
```

## Smoke-check

Без токена (должен быть 401):
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8787/v1/models" -Method Get
```

С токеном:
```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8787/v1/models" `
  -Method Get `
  -Headers @{ Authorization = "Bearer your_strong_bridge_token" }
```

Проксирование chat/completions:
```powershell
$body = @{
  model = "qwen2.5-7b-instruct"
  messages = @(
    @{ role = "user"; content = "ping" }
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8787/v1/chat/completions" `
  -Method Post `
  -Headers @{ Authorization = "Bearer your_strong_bridge_token" } `
  -ContentType "application/json" `
  -Body $body
```

