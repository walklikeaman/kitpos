# N8N Integration — Maverick Terminal Agent

## Архитектура

```
Telegram / Chat
      │
      ▼
┌─────────────────────────────────────────┐
│  N8N: KIT POS Assistant (Telegram)      │
│  mqr5AV6SxVZwJvsF — уже активен        │
│                                          │
│  Telegram Trigger                        │
│       │                                  │
│       ▼                                  │
│  AI Intent Node (Gemini 2.0 Flash)      │
│  Определяет тип задачи:                  │
│   "build_file"      → Maverick API       │
│   "merchant_lookup" → kit-pos-api        │
│   "status"          → Maverick /history  │
│   "general"         → kit-kb-chat RAG    │
│       │                                  │
│       ▼                                  │
│  HTTP Request → Maverick Agent API       │
│       │                                  │
│       ▼                                  │
│  Wait + Poll /jobs/{id}                  │
│       │                                  │
│       ▼                                  │
│  Telegram Reply (✅ done / ❌ error)      │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│  Maverick Agent API  (server.py)         │
│  FastAPI + Uvicorn на порту 8080         │
│                                          │
│  POST /provision    — запустить задачу   │
│  GET  /jobs/{id}    — статус задачи      │
│  GET  /history      — история запусков   │
│  GET  /history/check/{sn} — дубликат?   │
│  GET  /health       — health check       │
│       │                                  │
│       ▼                                  │
│  KIT Dashboard API  (Bearer token)       │
│  → VAR данные по MID                    │
│       │                                  │
│       ▼                                  │
│  PAX Store (headless Playwright)         │
│  → Create merchant                       │
│  → Create terminal                       │
│  → Push firmware                         │
│  → Push Template → BroadPOS TSYS Sierra  │
│  → Fill TSYS parameters                  │
└─────────────────────────────────────────┘
```

---

## Запуск сервера

```bash
cd agents/maverick-terminal-agent

# Установить зависимости
pip install -e '.[browser,server]'
python -m playwright install chromium

# Запустить API
python server.py
# или
uvicorn server:app --host 0.0.0.0 --port 8080

# С auto-reload для разработки
uvicorn server:app --reload --port 8080
```

Сервер читает те же env vars что и скрипт:
- `KIT_API_KEY` — для VAR данных
- `PAX_USERNAME` / `PAX_PASSWORD` — для PAX Store

---

## API Reference

### POST /provision

Запускает provisioning. Возвращает `job_id` сразу (async).

```json
{
  "merchant_number": "201100305938",
  "pinpad_serial": "2290664794",
  "pinpad_model": "A3700",
  "submit": true
}
```

Ответ:
```json
{
  "job_id": "a3f9b2c1",
  "status": "queued",
  "created_at": "2026-05-06T10:00:00Z"
}
```

### GET /jobs/{job_id}

Статус задачи. Статусы: `queued` → `running` → `success` / `failed`.

```json
{
  "job_id": "a3f9b2c1",
  "status": "success",
  "created_at": "2026-05-06T10:00:00Z",
  "finished_at": "2026-05-06T10:03:42Z",
  "result": {"output": "..."}
}
```

### GET /history/check/{serial}

Проверить не был ли SN уже провижонирован.

```json
{"provisioned": false, "last_run": null}
```

---

## N8N Workflow — Intent Parsing (AI Node)

### System prompt для AI Node

```
You are a KIT POS terminal provisioning assistant.
Parse the incoming message and extract the intent and parameters.

Return JSON:
{
  "intent": "build_file" | "merchant_lookup" | "status" | "general",
  "merchant_number": "...",    // 12-digit MID if mentioned
  "serial_number": "...",      // SN if mentioned
  "device_model": "A3700",     // PIN pad model, default A3700
  "var_v_number": "...",       // V-number if mentioned, else null
  "raw_message": "..."         // original message
}

Intent rules:
- "build_file": message contains SN + MID, or says "build", "install", "provision", "add terminal"
- "merchant_lookup": asks about a merchant, MID lookup, VAR data
- "status": asks about status, history, already provisioned?
- "general": anything else
```

### Build File N8N Flow (упрощённый)

```
Telegram Trigger
  → AI Intent Node
  → IF intent == "build_file"
      → HTTP Request: GET /history/check/{{serial_number}}
      → IF provisioned == true
          → Telegram: "⚠️ SN {{serial_number}} уже провижонирован. Подтверди повтор."
      → ELSE
          → HTTP Request: POST /provision
              body: {merchant_number, pinpad_serial, submit: true}
          → Wait 10s
          → HTTP Request: GET /jobs/{{job_id}}
          → IF status == "success"
              → Telegram: "✅ {{merchant_number}} — терминал добавлен"
          → ELSE IF status in ["running", "queued"]
              → Wait 30s → retry GET /jobs (до 10 попыток)
          → ELSE
              → Telegram: "❌ Ошибка: {{error}}"
```

---

## Разбор входящего сообщения

Пример сообщений, которые должен распознавать AI:

```
"Build the file MID 201100305938 Pady C Store SN 2290664794"
"Добавь терминал: MID 201100306001, SN 2630132073 (L1400) + 2620079273 (A3700)"
"Pady C Store 201100305938 — SN: 2290664794"
```

N8N AI node выдаёт структурированный JSON → HTTP запрос к Maverick API.

---

## Где хостить Maverick API

| Вариант | RAM | Стоимость | Playwright |
|---------|-----|-----------|------------|
| **Mac (локально)** | ✅ достаточно | бесплатно | ✅ |
| Render Standard | 2 GB | $7/мес | ✅ |
| Railway | 512 MB–8 GB | pay-per-use | ✅ |
| Render free tier | 512 MB | бесплатно | ❌ (мало RAM) |

**Сейчас:** запускать на Mac (сервер остаётся включённым).  
**Production:** отдельный Render Standard сервис (не тот где N8N).

---

## N8N Webhook для входящих задач (без Telegram)

Можно слать задачи напрямую через N8N webhook `kit-pos-api`:

```bash
curl -X POST https://n8n-1i79.onrender.com/webhook/kit-pos-api \
  -H "Content-Type: application/json" \
  -d '{
    "action": "build_file",
    "merchant_number": "201100305938",
    "pinpad_serial": "2290664794"
  }'
```

N8N принимает → парсит → вызывает `/provision` → ждёт → возвращает статус.
