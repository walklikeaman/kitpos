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

### Два базовых URL (оба работают)

| URL | Используется для |
|---|---|
| `https://dashboard.maverickpayments.com/api` | Merchant, Terminal, Boarding Application, Attachments — **используем этот** |
| `https://kitdashboard.com/api` | DBA (документация указывает этот URL для DBA) |
| `https://kitdashboard.com/merchant/profile/...` | UI-контроллер для лого и VAR PDF (требует сессию, не Bearer) |

**Auth (REST API):** `Authorization: Bearer {KIT_API_KEY}`
**Auth (UI-контроллер):** сессионный cookie (см. VarDownloader / MerchantBrandingService)

**Sandbox:** `https://sandbox.kitdashboard.com/api` (отдельный API-ключ)

### Ключевые эндпоинты

**Merchant (dashboard.maverickpayments.com/api):**
- `GET /merchant?filter[name][like]=X` — поиск по имени
- `GET /merchant/{id}` — по internal id
- `GET /merchant?per-page=50&page=N` — пагинация всех мерчантов (для поиска по MID)
- `GET /terminal?filter[merchant.id][eq]={id}` — терминалы мерчанта

**DBA (kitdashboard.com/api) — только чтение:**
- `GET /dba` — список всех DBA
- `GET /dba/{id}` — один DBA по id
- ⚠️ Нет PUT/POST/PATCH — DBA **read-only** через API

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

### ⚠️ Если встретился неизвестный Chain — полный автоматический протокол

CLI вернёт exit code **2** и JSON в stderr:
```json
{
  "event": "UNKNOWN_CHAIN",
  "merchant_name": "...",
  "unknown_chains": ["XXXXXX"],
  "action_required": "..."
}
```

Агент **обязан** выполнить следующие шаги **по порядку**, переходя
к следующему только если предыдущий не дал результата:

---

#### Шаг 1: Попробовать скачать VAR PDF через VarDownloader

```bash
merchant get-var-by-merchant-name "{merchant_name}" --save-dir ./tmp/var_learn
```

Если PDF скачан → перейти к **Шагу 4**.

---

#### Шаг 2: Поискать уведомление в Gmail

Использовать Gmail MCP (`search_threads`) с запросом:
```
from:no-reply@kitdashboard.com subject:"VAR available" "{merchant_name}"
```
или по MID если известен:
```
from:no-reply@kitdashboard.com subject:"VAR available" "{MID}"
```

Если письмо найдено — VAR есть на kitdashboard, но VarDownloader не смог
его получить. Попробовать снова с явным логином:
```bash
merchant get-var-by-merchant-name "{merchant_name}" --verification-code {если нужно}
```

Если PDF получен → перейти к **Шагу 4**.

---

#### Шаг 3: Диалог с пользователем

Если ни VarDownloader, ни Gmail не дали результата:

> "Встречен новый Chain: `{chain}` для мерчанта `{merchant_name}`.
> BIN для него неизвестен и не удалось найти VAR автоматически.
> Пожалуйста, пришли VAR-лист (PDF-файл или текст) для этого мерчанта
> или любого другого с Chain `{chain}`."

Дождаться ответа, взять файл/текст и перейти к **Шагу 4**.

---

#### Шаг 4: Извлечь BIN из VAR PDF и обновить таблицу

```python
from pdfminer.high_level import extract_text
import re
text = extract_text("path/to/var.pdf")
bin_val = re.search(r"BIN:\s*(\d+)", text).group(1)
chain_val = re.search(r"Chain:\s*(\d+)", text).group(1)
```

Добавить в `src/merchant_data/models.py` в словарь `_CHAIN_TO_BIN`:
```python
"{chain_val}": "{bin_val}",   # e.g. {merchant_name}
```

Закоммитить:
```bash
git add src/merchant_data/models.py
git commit -m "Learn chain→BIN: {chain_val}→{bin_val} ({merchant_name})"
git push origin main
```

---

#### Шаг 5: Повторить исходную команду

```bash
merchant api-var-by-mid {MID}
# или
merchant api-var-by-name "{merchant_name}"
```

Теперь BIN будет вычислен корректно.

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

## Gmail коннектор

Доступен MCP с инструментами `search_threads` и `get_thread`.

**Уведомления о VAR-листах** приходят от `no-reply@kitdashboard.com`
с темой `"VAR available"` и содержат MID и DBA в теле письма.
Они **не содержат PDF-вложение** — только уведомление что VAR загружен.

Полезные запросы:
```
# Найти VAR для конкретного мерчанта
from:no-reply@kitdashboard.com subject:"VAR available" "El Camino"
from:no-reply@kitdashboard.com subject:"VAR available" "201100300996"

# Все VAR-уведомления
from:no-reply@kitdashboard.com subject:"VAR available"

# 2FA коды (если нужен код для логина)
from:no-reply@kitdashboard.com subject:"verification" newer_than:5m
```

---

## Коды штатов (_STATE_CODES) — важно

Maverick API возвращает штат как целое число (`address.state`).
Маппинг — строгий алфавитный порядок 50 штатов + DC, где **DC стоит на позиции 9**
(alphabetically: Delaware=8, **District of Columbia=9**, Florida=10, …).

Это ≠ наивный алфавитный порядок без DC — из-за DC все штаты от Florida и далее
сдвинуты на +1 относительно простого алфавитного списка.

Верификация (из реальных мерчантов):
- state=11 + zip=30458 → **Georgia** ✓ (Statesboro Vape Shop, GA)
- state=37 + zip=73703 → **Oklahoma** ✓ (Enid, OK)

Полная таблица определена в `models.py` → `_STATE_CODES`.
Не менять без проверки реальными мерчантами.

---

## Адрес: валидация штата по ZIP-коду

`models.py` содержит функцию `validate_state_from_zip(zip_code, state_name)`.
При несовпадении первых 3 цифр ZIP с ожидаемым штатом — выдаёт предупреждение в stderr.

Это не блокирует работу — только предупреждает. Несовпадение может означать:
- Ошибочный штат в API (`_STATE_CODES` неверен для этого мерчанта)
- Мерчант зарегистрирован в одном штате, работает в другом (редко)
- Ошибка в данных самого мерчанта

При обнаружении несоответствия — проверить реальный адрес через дашборд.

---

## Email мерчанта: где какие поля существуют

### Карта email-полей по объектам API

| Поле | Объект | Readonly | Примечание |
|---|---|---|---|
| `customerServiceContact.email` | **DBA** (активный мерчант) | Yes | Единственный email в DBA API |
| `customerServiceContact.email` | Boarding Application | No | То же поле, заполняется при онбординге |
| `corporateContact.email` | **только** Boarding Application | No | Отсутствует в DBA API |
| `principals[N].email` | **только** Boarding Application | No | Отсутствует в DBA API |

> ⚠️ `corporateContact` и `principals.email` — **нет в DBA/Merchant API**, только в Boarding Application.
> Не пытаться искать их в ответе `GET /merchant` или `GET /dba`.

### Уровень 1: DBA / Merchant API

```
merchant.dbas[0].customerServiceContact.email
```
Это "Support Email" в дашборде. Часто не заполнен.

### Уровень 2: Boarding Application (fallback)

Если Merchant API не вернул email — ищем в заявке на онбординг.
Запрос: `GET /boarding-application?filter[company.name][like]={merchant_name}`

Проверяются три поля **по приоритету**:

| Приоритет | Поле | Примечание |
|---|---|---|
| 1 | `customerServiceContact.email` | "Support Email" — предпочтительный |
| 2 | `corporateContact.email` | Корпоративный контакт |
| 3 | `principals[N].email` | Личный email принципала (последний вариант) |

Берётся первое непустое значение. Реализовано в `kit_api.py` → `_email_from_boarding()`.

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

## Онбординг мерчантов: обязательные правила

> Эти правила применяются при создании/обновлении заявки через `MerchantOnboardingService`.

### Тип бизнеса (entity_type)

Определяется из документов мерчанта (DBA/Voided Check/Договор). Правила:

| Что написано в документах | entity_type |
|---|---|
| "Inc", "Corp", "Corporation" | `"Corporation"` |
| "LLC" | `"LLC"` |
| "Sole proprietor" / физлицо без юрлица | `"SoleProprietorship"` |
| "Partnership", "LP", "LLP" | `"Partnership"` |

Никогда не угадывать — брать точно из документов.

### Звание принципала (title)

- **По умолчанию: `"CEO"`** — если в документах не указано иное.
- Если явно написано President, Manager, Partner — использовать это.
- **Никогда не использовать `"Owner"`** — это устаревшее поле, API принимает, но KIT не использует.
- Для LLC с одним владельцем: `"CEO"` (не "Member", не "Manager").

### Платёжные системы (intendedUsage)

По умолчанию при онбординге **все три** должны быть включены:

| Поле | Дефолт | Примечание |
|---|---|---|
| `accept_credit` | `True` | VISA, MC, Discover |
| `accept_pin_debit` | `True` | PIN Debit |
| `accept_amex` | **`True`** | AMEX OptBlue — **обязательно включать** |
| `accept_ebt` | `False` | Только если мерчант явно запросил |

> **AMEX OptBlue** = поле `processing.intendedUsage.amex.optBlue = "Yes"`.
> Включается через `profile.accept_amex = True`.

### Имя принципала

- **Не использовать среднее имя** — только First + Last.
- Брать из Driver's License: поле LAST NAME + FIRST NAME.
- Игнорировать отчество/middle name даже если оно есть в документе.

### Документы (Driver License и Voided Check)

- DL сканируется через `pdf2image` → PNG, затем визуальный OCR (pdfplumber ломается на защищённых DL).
- Voided Check: Routing + Account из чека. **Routing всегда 9 цифр.**
- Типы документов задаются через `set_document_type()` (integer ID, не строка):
  - `DOCUMENT_TYPE_VOIDED_CHECK = 6`
  - `DOCUMENT_TYPE_DRIVER_LICENSE = 18`
  - `DOCUMENT_TYPE_OTHER = 3`

### Стандартные параметры заявки (KIT POS)

```python
campaign_id = 1579       # KIT POS InterCharge Plus
mcc_id = 5912            # Drug Stores / Convenience (самый частый для KIT POS)
equipment_used = "KIT POS"
building_type = "Office Building"
building_ownership = "Rents"
area_zoned = "Commercial"
sales_split = swiped=100, mail=0, internet=0
```

---

## Система логирования запусков (runs/)

**Каждый** запуск онбординга (успешный или нет) обязан быть залогирован:

```python
from merchant_data.services.run_logger import RunLogger
log = RunLogger()

# При успехе:
log.success(
    merchant_name="...",
    app_id=756692,
    source_pdf="file.pdf",
    principal_name="Ali Alomari",
    entity_type="Corporation",
    documents=["driver_license.png", "voided_check.png"],
    notes="Любые нестандартные ситуации или решения",
)

# При ошибке:
log.failure(
    merchant_name="...",
    source_pdf="file.pdf",
    reason="Не удалось распарсить EIN",
    error="re.search returned None",
    app_id=None,  # если заявка была создана но упала
)
```

Файл логов: `runs/runs.jsonl` (append-only JSONL, не коммитится в git).

Просмотр истории:
```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from merchant_data.services.run_logger import RunLogger
print(RunLogger().summary())
"
```

**Правила:**
- Логировать ВСЕГДА — даже если заявка создана но не заполнена.
- В `notes` писать всё нестандартное: что было не так, как решили.
- Логи — основа для улучшений. Без логов — нет обучения.

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
| 2026-05-02 | Онбординг: upload_attachment, link_document, set_document_type (about=[int]) |
| 2026-05-02 | Онбординг: исправлен base URL на kitdashboard.com |
| 2026-05-02 | Онбординг: document type IDs: 6=VoidedCheck, 18=DriverLicense |
| 2026-05-02 | Онбординг: дефолт accept_amex=True (AMEX OptBlue включён по умолчанию) |
| 2026-05-02 | Правила: title дефолт CEO, не Owner; no middle name |
| 2026-05-02 | RunLogger: система логирования запусков (runs/runs.jsonl) |
| 2026-05-02 | Первый успешный полный запуск: El Camino Mart Inc → app_id=756692 |
| 2026-05-05 | Исправлен `_STATE_CODES`: DC на позиции 9 (не 51); сдвинуты FL=10, GA=11 и далее |
| 2026-05-05 | Добавлена валидация адреса: ZIP-prefix → ожидаемый штат (`validate_state_from_zip`) |
| 2026-05-05 | Email fallback: если нет в Merchant API → ищем в boarding-application (3 поля) |
| 2026-05-05 | `_parse()`: в адрес добавлен штат (раньше отсутствовал) |
| 2026-05-05 | Skill `kit-merchant-lookup` создан для Claude Code |
| 2026-05-05 | Уточнены URL: DBA API → kitdashboard.com/api; лого → kitdashboard.com/merchant/profile/ (UI-сессия) |
| 2026-05-05 | Карта email-полей: corporateContact.email и principals.email только в Boarding App, не в DBA API |
| 2026-05-05 | MerchantBrandingService: upload-logo / remove-logo команды (multipart POST через UI-сессию) |
