# KIT POS — Full System Handoff

> **Для агентов в смежных репозиториях.** Здесь всё необходимое для подключения к инфраструктуре KIT POS.  
> Реальные ключи — в файле `.env` в корне этого репозитория (gitignored).  
> Дата: 2026-05-06. Обновляй этот файл при добавлении новых credentials/эндпоинтов.

---

## Где взять реальные ключи

Все секреты лежат в файле **`/Users/walklikeaman/GitHub/kitpos/.env`** (gitignored, не попадает в репо).  
Попроси владельца прислать этот файл или скопируй из переменных ниже.

Также все ключи задокументированы в Claude memory:  
`~/.claude/projects/-Users-walklikeaman-GitHub-kitpos/memory/n8n_credentials.md`

---

## 1. Supabase RAG Knowledge Base

**Основная база знаний** — все FAQ, письма поддержки, API-документация, PDF-инструкции, данные мерчантов.

| Параметр | Значение |
|----------|----------|
| Project ID | `hoowbtzdzndvyihxhlpb` |
| URL | `https://hoowbtzdzndvyihxhlpb.supabase.co` |
| Anon Key | см. `SUPABASE_KEY` в `.env` |
| Table | `documents` |
| Vector dims | `1536` (pgvector, HNSW index) |
| Search function | `match_documents(query_embedding, match_threshold, match_count)` |

### Структура таблицы `documents`

```sql
id           bigserial PRIMARY KEY
source       text          -- e.g. "email:Inbox:42", "pdf:filename.pdf", "chat:whatsapp"
source_type  text          -- "email" | "pdf" | "text" | "chat"
title        text
content      text          -- текстовый чанк
metadata     jsonb         -- произвольные поля (from, subject, date, chunk, total_chunks, ...)
embedding    vector(1536)
created_at   timestamptz
```

### Как делать семантический поиск

```python
import requests, os

SUPABASE_URL = "https://hoowbtzdzndvyihxhlpb.supabase.co"
SUPABASE_KEY = os.environ["SUPABASE_KEY"]     # anon key из .env
OPENROUTER_KEY = os.environ["OPENROUTER_API_KEY"]

def search_kb(query: str, threshold=0.5, count=5):
    # 1. Получить embedding запроса
    emb_r = requests.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
        json={"model": "openai/text-embedding-3-small", "input": query}
    )
    embedding = emb_r.json()["data"][0]["embedding"]

    # 2. Поиск по базе
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/match_documents",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                 "Content-Type": "application/json"},
        json={"query_embedding": embedding, "match_threshold": threshold, "match_count": count}
    )
    return r.json()  # list of {id, source, title, content, metadata, similarity}
```

### Текущий объём базы (2026-05-06)

| source_type | чанков |
|-------------|--------|
| chat        | ~97    |
| text        | ~88    |
| pdf         | ~66    |
| email       | идёт заливка (2404 писем из Google Takeout) |

---

## 2. OpenRouter (Embeddings + LLM)

| Параметр | Значение |
|----------|----------|
| API Key | `OPENROUTER_API_KEY` в `.env` |
| Base URL | `https://openrouter.ai/api/v1` |
| Embed model | `openai/text-embedding-3-small` (1536 dims, $0.02/1M tokens) |
| Chat model (N8N) | `google/gemini-2.0-flash-001` |

```bash
# Пример — получить embedding (подставь ключ из .env)
curl https://openrouter.ai/api/v1/embeddings \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/text-embedding-3-small","input":"ваш текст"}'
```

---

## 3. N8N Automation

| Параметр | Значение |
|----------|----------|
| URL | `https://n8n-1i79.onrender.com` |
| API Key | `N8N_API_KEY` в `.env` |
| Header | `X-N8N-API-KEY: <key>` |
| MCP endpoint | `https://n8n-1i79.onrender.com/mcp-server/http` (Bearer = API Key) |

### Активные Webhook'и

| Webhook URL | Метод | Назначение |
|-------------|-------|-----------|
| `https://n8n-1i79.onrender.com/webhook/kit-pos-api` | POST | Merchant lookup |
| `https://n8n-1i79.onrender.com/webhook/kit-kb-chat` | POST | RAG Knowledge Base чат |

#### kit-pos-api — формат запроса

```json
{"action": "lookup_mid", "mid": "123456789"}
```

Поддерживаемые `action`:
- `status` — статус агента
- `lookup_name` — поиск по имени (`"name": "..."`)
- `lookup_mid` — поиск по MID (`"mid": "..."`)
- `var_list` — JSON VAR-данные (`"terminal_id": "..."`)
- `get_terminals` — список терминалов (`"merchant_id": "..."`)

#### kit-kb-chat — формат запроса

```json
{"message": "Как сделать онбординг мерчанта?"}
```

Возвращает: `{"answer": "...", "sources": [...]}`

### Активные Workflows

| ID | Название | Статус |
|----|----------|--------|
| `iKTaNQQ6SqeQynSX` | KIT POS Chat API | ✅ Active |
| `mqr5AV6SxVZwJvsF` | KIT POS Assistant (Telegram) | ✅ Active |
| `bNTtHVGVRJabaw9c` | KIT KB Chat (RAG) | ✅ Active |

### N8N Internal Credential IDs

| ID | Тип | Назначение |
|----|-----|-----------|
| `abGkKP1iH0Km4dSW` | httpHeaderAuth | KIT Maverick API |
| `TZccT3B7YAZfq4BU` | openRouterApi | OpenRouter account |
| `nJuEgEKvtlm2Pvkv` | httpHeaderAuth | OpenRouter HTTP |
| `PzLBd3oJDZXGEyC0` | telegramApi | Telegram account |

---

## 4. KIT Dashboard API

| Параметр | Значение |
|----------|----------|
| API Key | `KIT_API_KEY` в `.env` |
| Base URL (основной) | `https://dashboard.maverickpayments.com/api` |
| Base URL (DBA) | `https://kitdashboard.com/api` |
| Auth header | `Authorization: Bearer $KIT_API_KEY` |
| Дополнительные headers | `Referer: https://kitdashboard.com/`, browser User-Agent |

> ⚠️ Cloudflare блокирует Python User-Agent. Всегда передавай browser UA.

### Ключевые эндпоинты

```bash
# Поиск мерчанта по имени
GET /merchant?filter[name][like]=SomeMerchant&page[size]=10

# Мерчант по ID
GET /merchant/<id>

# Список терминалов мерчанта
GET /terminal?filter[merchant.id][eq]=<merchant_id>

# VAR данные по терминалу (JSON)
GET /terminal/<terminal_id>/var-list

# VAR PDF по терминалу
GET /terminal/<terminal_id>/var-download

# Список заявок на онбординг
GET /boarding-application

# Создать заявку
POST /boarding-application/create
Body: {"campaign":{"id":"<campaign_id>"},"processingMethod":"<method>"}

# Обновить заявку
PUT /boarding-application/<id>

# Валидировать заявку ([] = OK, dict = ошибки)
GET /boarding-application/<id>/validate
```

### Права текущего ключа

- ✅ Читать: /merchant, /boarding-application, /dba, /terminals, /reporting, /ach
- ✅ Писать: POST+PUT /boarding-application (создание и заполнение)
- ❌ Запрещено: DELETE /boarding-application, PUT /status/*, все /ach write

---

## 5. Render Infrastructure

| Параметр | Значение |
|----------|----------|
| API Key | `RENDER_API_KEY` в `.env` |
| N8N Service ID | `srv-d7sjk40k1i2s739r4jbg` |
| API Base | `https://api.render.com/v1/` |

```bash
# Перезапустить N8N сервис
curl -X POST https://api.render.com/v1/services/srv-d7sjk40k1i2s739r4jbg/restart \
  -H "Authorization: Bearer $RENDER_API_KEY"
```

---

## 6. Скрипты инжекции данных в Supabase

Все скрипты находятся в `scripts/` этого репозитория.

### `ingest_email.py` — залить mbox в Supabase

```bash
# Пакетный режим (рекомендуется — предотвращает OOM)
./scripts/ingest_email_batch.sh /path/to/Inbox.mbox

# С продолжением с позиции N
./scripts/ingest_email_batch.sh /path/to/Inbox.mbox --start=500

# Один прогон без батчинга
python3 -u scripts/ingest_email.py /path/to/Inbox.mbox --start=0 --limit=80

# Тест без записи в БД
python3 -u scripts/ingest_email.py /path/to/Inbox.mbox --dry-run
```

**Что делает**: парсит mbox через mmap (no OOM), чистит тело письма, чанкует по 2000 символов,  
получает embedding через OpenRouter, вставляет в Supabase `documents`.

**Фильтры**: пропускает письма >60KB, от amazon.com/google.com/shop.app и короче 60 символов.

**Важно**: запускай из своего терминала (не через CI/bash sandbox с ограниченной памятью).

---

## 7. Архитектурные ограничения

| Компонент | Ограничение |
|-----------|-------------|
| N8N on Render | **512 MB RAM** — минимизировать параллельные executions |
| PostgreSQL on Render | **1 GB storage**, истекает ~август 2026 |
| Supabase free | 500 MB database, 50K векторов |
| N8N Code nodes | `require('https')` работает (task runner отключён) |

**Правила**:
- ❌ Не запускать несколько Telegram trigger workflows одновременно
- ❌ Не хранить бинарники в N8N execution history  
- ❌ Не добавлять секреты как env vars в Render (вызывает redeploy)
- ✅ Credentials хранить внутри N8N (не в env)

---

## 8. Repo Structure

```
kitpos/
├── agents/
│   ├── maverick-terminal-agent/      # PAX Store provisioning
│   ├── kit-dashboard-merchant-data/  # VAR lookup + logo upload
│   └── kit-dashboard-agent/          # Merchant onboarding docs
├── scripts/
│   ├── ingest_email.py               # mbox → Supabase (mmap-based)
│   ├── ingest_email_batch.sh         # batch runner (prevents OOM)
│   └── ingest_to_supabase.py         # general ingestion (PDF, text, JSON)
├── docs/
├── merchants.csv / merchants.json    # snapshot мерчантов
├── applications.csv / .json          # snapshot заявок
├── .env                              # 🔑 реальные ключи (gitignored)
└── HANDOFF.md                        # этот файл
```

---

## 9. .env — шаблон файла с ключами

Скопируй и заполни реальными значениями (запроси у владельца репозитория):

```bash
# Supabase
SUPABASE_URL=https://hoowbtzdzndvyihxhlpb.supabase.co
SUPABASE_KEY=<anon key — спроси у владельца>

# OpenRouter
OPENROUTER_API_KEY=<sk-or-v1-... — спроси у владельца>

# KIT Dashboard
KIT_API_KEY=<kjQ0.... — спроси у владельца>

# N8N
N8N_URL=https://n8n-1i79.onrender.com
N8N_API_KEY=<eyJ... — спроси у владельца>

# Render
RENDER_API_KEY=<rnd_... — спроси у владельца>
RENDER_SERVICE_ID=srv-d7sjk40k1i2s739r4jbg
```

---

## 10. Быстрый тест подключения

```bash
source .env  # загрузить ключи

# Supabase — проверить таблицу documents
curl "$SUPABASE_URL/rest/v1/documents?select=source_type&limit=1" \
  -H "apikey: $SUPABASE_KEY"

# N8N — статус агента
curl -X POST https://n8n-1i79.onrender.com/webhook/kit-pos-api \
  -H "Content-Type: application/json" \
  -d '{"action":"status"}'

# KIT Dashboard — список мерчантов
curl "https://dashboard.maverickpayments.com/api/merchant?page[size]=3" \
  -H "Authorization: Bearer $KIT_API_KEY" \
  -H "User-Agent: Mozilla/5.0"
```

---

## 11. Claude Desktop MCP Config

Для подключения N8N как MCP-сервера добавь в `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "n8n": {
      "type": "http",
      "url": "https://n8n-1i79.onrender.com/mcp-server/http",
      "headers": {
        "Authorization": "Bearer <N8N_API_KEY из .env>"
      }
    }
  }
}
```
