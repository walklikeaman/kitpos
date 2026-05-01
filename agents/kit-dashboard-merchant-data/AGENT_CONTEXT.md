# Agent Context: KIT Dashboard Merchant Data

> **Для AI-агентов.** Прочитай этот файл полностью перед любым действием.
> Он описывает как работает система, какие данные где хранятся, и как действовать
> в нестандартных ситуациях. Следуй инструкциям точно.

---

## Что делает этот пакет

Извлекает данные мерчантов KIT POS (имя, адрес, телефон, MCC, терминалы, VAR-данные)
через Maverick Payments REST API. **Браузер не нужен** для большинства операций.

Работа с данными:
- **`api-var-by-mid` / `api-var-by-name`** — полные VAR-данные (все поля VAR-листа)
  из API без браузера, без сессии, без PDF
- **`api-by-mid` / `api-by-name` / `api-by-internal-id`** — базовые данные мерчанта
- **`get-var-by-mid` / `get-var-by-merchant-name`** — скачать VAR как PDF-файл
  (нужна сессия kitdashboard.com)

---

## Установка и запуск

```bash
cd agents/kit-dashboard-merchant-data
pip install -e .           # установить пакет
cp .env.example .env       # заполнить KIT_EMAIL, KIT_PASSWORD, KIT_API_KEY
merchant --help            # список команд
```

### Переменные окружения (`.env`)

```
KIT_EMAIL=nikita@kit-pos.com
KIT_PASSWORD=...
KIT_API_KEY=kjQ0.nAcSa5fkt85ytxm4FJn4ZyY0KL6XHPhS
```

`.env` не коммитится в git.

---

## CLI команды

### Основные (API, мгновенно, без браузера)

```bash
# VAR-данные по MID (рекомендуется)
merchant api-var-by-mid 201100300996
merchant api-var-by-mid 201100300996 --json

# VAR-данные по имени мерчанта
merchant api-var-by-name "El Camino"
merchant api-var-by-name "El Camino" --json

# Базовые данные мерчанта
merchant api-by-mid 201100300996
merchant api-by-name "El Camino"
merchant api-by-internal-id 299390
```

### Скачать VAR PDF (нужна сессия)

```bash
merchant get-var-by-mid 201100300996 --save-dir ./downloads
merchant get-var-by-merchant-name "El Camino" --save-dir ./downloads
```

---

## Архитектура

```
src/merchant_data/
  models.py              — VarData, MerchantResult, KitCredentials, VarDownloadResult
                           + _CHAIN_TO_BIN (таблица Chain → BIN)
                           + _STATE_CODES  (код штата → название)
  services/
    kit_api.py           — MerchantAPIService: все API-запросы
    kit_var_downloader.py— VarDownloader: HTTP-логин + PDF скачивание
    kit_merchant_lookup.py — MerchantLookupService: Playwright (legacy)
  cli.py                 — typer CLI
```

**API base URL:** `https://dashboard.maverickpayments.com/api`
**Auth:** `Authorization: Bearer {KIT_API_KEY}`

Ключевые эндпоинты:
- `GET /merchant?filter[name][like]=X` — поиск по имени
- `GET /merchant/{id}` — по internal id
- `GET /merchant?per-page=50&page=N` — пагинация всех мерчантов (для поиска по MID)
- `GET /terminal?filter[merchant.id][eq]={id}` — терминалы мерчанта

> ⚠️ `filter[dbas.processing.mid]` в API **сломан** (возвращает 422).
> Для поиска по MID — пагинировать всех мерчантов (~13 страниц по 50) и искать локально.

---

## VAR-данные: как устроены

VAR-лист (TSYS VAR/Download Sheet) содержит:

| Поле | Источник в API | Примечание |
|---|---|---|
| Legal Name | `merchant.name` | |
| DBA | `merchant.dbas[0].name` | |
| Street / City / ZIP | `merchant.dbas[0].address` | |
| State | `merchant.dbas[0].address.state` | Код → название через `_STATE_CODES` |
| Phone | `merchant.dbas[0].customerServiceContact.phone` | |
| Merchant # (MID) | `merchant.dbas[0].processing.mid` | |
| V Number | `terminal.backendProcessorId` | |
| MCC | `merchant.dbas[0].mcc` | |
| Chain | `terminal.chain` | |
| Agent Bank | `terminal.agentBank` | |
| Store # | `terminal.storeNumber` | |
| Terminal # | `terminal.tid` | |
| Location # | `terminal.locationNumber` | |
| Monthly Volume | `processing.volumes.monthlyTransactionAmount` | |
| Card types | `terminal.acceptVisa/MC/Amex/...` | |
| **BIN** | **вычисляется из `terminal.chain`** | См. таблицу ниже |

---

## Таблица Chain → BIN (критически важно)

BIN (Bank Identification Number) в VAR не хранится в API.
Он **однозначно определяется** значением `terminal.chain`:

```python
_CHAIN_TO_BIN = {
    "081960": "422108",   # FFB Bank — основная группа (~90% мерчантов)
    "261960": "442114",   # e.g. Ali Baba Smoke and Gift Shop
    "051960": "403982",   # e.g. Holy Smokes Smoke Shop
}
```

Таблица выведена из анализа 11+ реальных VAR-листов (май 2026).

### ⚠️ Если встретился неизвестный Chain

Если `terminal.chain` не найден в `_CHAIN_TO_BIN`, агент **обязан**:

1. Сообщить пользователю:
   > "Встречен новый Chain: `{chain}`. BIN для него неизвестен.
   > Пожалуйста, пришли VAR-лист для любого мерчанта с этим Chain
   > (PDF или текст), чтобы я мог обновить таблицу."

2. Дождаться VAR-листа от пользователя.

3. Найти в нём строку `BIN: XXXXXX` и строку `Chain: YYYYYY`.

4. Добавить новую запись в `_CHAIN_TO_BIN` в файле
   `src/merchant_data/models.py`:
   ```python
   "YYYYYY": "XXXXXX",   # e.g. <merchant name>
   ```

5. Закоммитить:
   ```bash
   git add src/merchant_data/models.py
   git commit -m "Add chain→BIN mapping: {chain}→{bin} ({merchant name})"
   git push origin main
   ```

6. Повторить исходный запрос — теперь BIN будет вычислен корректно.

---

## Сессия kitdashboard.com (только для PDF-скачивания)

Для `get-var-by-mid` / `get-var-by-merchant-name` нужна сессия.

**Как получить сессию (первый раз / истекла):**

Сессия создаётся автоматически при первом обращении через HTTP-логин:
1. GET `/login` → CSRF токен
2. POST credentials → если 2FA, ждёт код
3. Сохраняет все куки в `tmp/kit-merchant-state.json`

**2FA (только при первом логине на новом устройстве):**

Агент пишет `tmp/2fa_requested.txt` и ждёт 90 секунд.
Нужно записать код в `tmp/2fa_code.txt`:
```bash
echo "123456" > tmp/2fa_code.txt
```

**Повторный логин без 2FA:**

Куки `deviceId` и `tsv_*` из сохранённой сессии говорят серверу
"доверенное устройство" — 2FA пропускается автоматически.
Сессия живёт ~30–90 дней (пока `tsv_*` не истечёт).

**Путь к кукам:** `tmp/kit-merchant-state.json`

> Эти файлы не коммитятся в git.

---

## Как устроен VAR PDF (для справки)

VAR скачивается по URL:
```
https://kitdashboard.com/merchant/profile/view-var-sheet?id={merchantAccountId}&terminalId={terminalId}
```

> ⚠️ `merchantAccountId` ≠ `merchant.id` из API.
> `merchantAccountId` = `processing.id` из API (поле `merchant.dbas[0].processing.id`).
> Код получает его из HTML профиль-страницы, а не из API напрямую.

---

## Обучение на новых данных: правила

Каждый раз когда агент обрабатывает новый VAR-лист (PDF или текст),
он должен проверить:

1. **Chain уже в таблице?** Если нет — добавить и закоммитить (см. выше).

2. **State code корректен?** `_STATE_CODES` покрывает 50 штатов + DC.
   Если встретился неизвестный код — спросить пользователя и добавить.

3. **Поля совпадают с ожидаемой структурой?** Если VAR-лист отличается
   от ожидаемого формата (новые поля, другая структура) — сообщить пользователю
   и предложить обновить парсер.

4. **После любого обновления таблиц — git commit + push.**

---

## Что не нужно делать

- **Не модифицировать** папку `kit-dashboard-agent/` (read-only reference)
- **Не коммитить** `.env`, `tmp/`, `debug/`, `downloads/`
- **Не использовать Playwright** для получения данных мерчанта — всё через API
- **Не скачивать PDF** если нужны только данные — использовать `api-var-by-mid`

---

## История изменений

| Дата | Что сделано |
|---|---|
| 2026-04-28 | Первая версия: Playwright + браузерный логин |
| 2026-04-29 | Миграция на Maverick REST API для данных мерчанта |
| 2026-05-01 | Гибридный VarDownloader: API + session cookie для PDF |
| 2026-05-01 | Исправлен VAR URL: `merchantAccountId` ≠ `merchant.id` |
| 2026-05-01 | HTTP-логин без браузера, device trust для пропуска 2FA |
| 2026-05-01 | `api-var-by-mid/name`: все VAR-данные из API, PDF не нужен |
| 2026-05-01 | Таблица Chain→BIN: 3 значения из анализа 11 VAR-листов |
