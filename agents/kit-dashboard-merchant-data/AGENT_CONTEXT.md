# Agent Context: KIT Dashboard Merchant Data

> **Для AI-агентов.** Прочитай этот файл полностью перед любым действием.
> Он описывает как работает система, какие данные где хранятся, и как действовать
> в нестандартных ситуациях. Следуй инструкциям точно.

---

## Что делает этот пакет

Извлекает данные мерчантов KIT POS (имя, адрес, телефон, MCC, терминалы, VAR-данные)
через Maverick Payments REST API. **Браузер не нужен.** Сессия не нужна для VAR.

### Приоритет получения VAR-данных (от лучшего к худшему)

```
1. GET /terminal/{id}/var-list   ← PRIMARY: JSON, Bearer только, BIN возвращается напрямую
2. GET /terminal/{id}/var-download ← PDF через API, Bearer только, без сессии
3. Вручную предоставленный PDF   ← если пользователь прислал файл
4. UI-сессия (VarDownloader)     ← устаревший метод, только если всё выше не сработало
```

> ✅ Gmail проверять **не нужно**. Эндпоинт `var-list` всегда доступен через Bearer токен.

Работа с данными:
- **`api-var-by-mid` / `api-var-by-name`** — полные VAR-данные из API, без сессии, без PDF
- **`api-by-mid` / `api-by-name` / `api-by-internal-id`** — базовые данные мерчанта
- **`get-var-by-mid` / `get-var-by-merchant-name`** — скачать VAR PDF через API (Bearer, без сессии)
- **`upload-logo` / `remove-logo`** — загрузить/удалить лого мерчанта (нужна сессия)

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

### VAR-данные (API, мгновенно, только Bearer — сессия не нужна)

```bash
# ✅ РЕКОМЕНДУЕТСЯ: VAR JSON по MID (BIN возвращается напрямую из API)
merchant api-var-by-mid 201100300996
merchant api-var-by-mid 201100300996 --json

# VAR JSON по имени мерчанта
merchant api-var-by-name "El Camino"
merchant api-var-by-name "El Camino" --json

# Скачать VAR PDF через API (Bearer, без сессии)
merchant get-var-by-mid 201100300996 --save-dir ./downloads
merchant get-var-by-merchant-name "El Camino" --save-dir ./downloads
```

### Базовые данные мерчанта

```bash
merchant api-by-mid 201100300996
merchant api-by-name "El Camino"
merchant api-by-internal-id 299390
```

### Лого мерчанта (нужна сессия kitdashboard.com)

```bash
merchant upload-logo logo.png --name "Snack Zone"
merchant upload-logo logo.png --mid 201100306415
merchant upload-logo logo.png --internal-id 303608
merchant remove-logo --name "Snack Zone"
```

---

## Архитектура

```
src/merchant_data/
  models.py                — VarData, MerchantResult, KitCredentials, VarDownloadResult
                             + _CHAIN_TO_BIN (Chain → BIN, fallback если API недоступен)
                             + _STATE_CODES  (код штата → название)
                             + validate_state_from_zip()
  services/
    kit_api.py             — MerchantAPIService: все REST API запросы
                             + var_json_by_terminal_id()   ← PRIMARY VAR метод
                             + var_pdf_by_terminal_id()    ← PDF через API (Bearer)
                             + var_data_by_mid/name()      ← используют var-list внутри
    kit_branding.py        — MerchantBrandingService: upload/remove logo (UI-сессия)
    kit_var_downloader.py  — VarDownloader: HTTP-логин + PDF (устаревший fallback)
    kit_merchant_lookup.py — MerchantLookupService: Playwright (legacy, не использовать)
  cli.py                   — typer CLI
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

**VAR — прямые эндпоинты (Bearer, без сессии):**
- `GET /terminal/{terminal_id}/var-list` — ✅ **PRIMARY**: все VAR поля как JSON, включая BIN
- `GET /terminal/{terminal_id}/var-download` — PDF файл напрямую (Bearer, без сессии)

> ⚠️ `terminal_id` — это **внутренний API id** (например `812330`), НЕ TID (7000) и НЕ V-номер.
> Получить: `GET /terminal?filter[merchant.id][eq]={merchant_internal_id}` → `items[0].id`

**DBA (kitdashboard.com/api) — только чтение:**
- `GET /dba` — список всех DBA
- `GET /dba/{id}` — один DBA по id
- ⚠️ Нет PUT/POST/PATCH — DBA **read-only** через API

> ⚠️ `filter[dbas.processing.mid]` в API **сломан** (возвращает 422).
> Для поиска по MID — пагинировать всех мерчантов (~13 страниц по 50) и искать локально.

---

## VAR-данные: как устроены

### Источник данных — `/terminal/{id}/var-list` (PRIMARY)

Эндпоинт возвращает все поля VAR-листа напрямую. **BIN возвращается как поле**, не нужно вычислять из chain.

Пример ответа:
```json
{
  "id": 812330,
  "tid": 7000,
  "backendProcessorId": "V6592346",
  "merchantNumber": 201100306415,
  "chain": "081960",
  "agentBank": "081960",
  "bin": "422108",
  "mcc": 5411,
  "storeNumber": "0001",
  "locationNumber": "00001",
  "approvedMonthlyVolume": "$50,000.00",
  "address": {
    "streetAddress": "604 Red Hill Ave",
    "city": "San Anselmo",
    "state": "California",
    "zip": "94960"
  },
  "customerServicePhone": "+1 510-640-2004",
  "acceptVisa": "Yes",
  "acceptMastercard": "Yes",
  "acceptDiscover": "Yes",
  "acceptAmericanExpress": "Yes",
  "acceptPinDebit": "Yes",
  "acceptEbt": "Yes",
  "acceptGiftCard": "No",
  "dba": { "id": 345680, "name": "Snack Zone" },
  "merchant": { "id": 303608, "name": "Snack Zone Inc" }
}
```

### Маппинг полей VAR-листа (TSYS)

| Поле VAR-листа | Источник в var-list | Примечание |
|---|---|---|
| Legal Name | `merchant.name` | |
| DBA | `dba.name` | |
| Street / City / ZIP | `address.streetAddress/city/zip` | |
| State | `address.state` | Уже строка ("California"), не код |
| Phone | `customerServicePhone` | |
| Merchant # (MID) | `merchantNumber` | |
| V Number | `backendProcessorId` | |
| MCC | `mcc` | |
| Chain | `chain` | |
| Agent Bank | `agentBank` | |
| Store # | `storeNumber` | |
| Terminal # | `tid` | |
| Location # | `locationNumber` | |
| Monthly Volume | `approvedMonthlyVolume` | |
| Card types | `acceptVisa/Mastercard/Amex/...` | |
| **BIN** | **`bin`** | ✅ Возвращается напрямую, не вычисляется |

---

## Таблица Chain → BIN (fallback, не используется если есть var-list)

> ✅ **BIN теперь возвращается напрямую** из `GET /terminal/{id}/var-list` в поле `bin`.
> Таблица ниже нужна **только** если var-list недоступен (исторический fallback).

```python
_CHAIN_TO_BIN = {
    "081960": "422108",   # FFB Bank — основная группа (~90% мерчантов)
    "261960": "442114",   # e.g. Ali Baba Smoke and Gift Shop
    "051960": "403982",   # e.g. Holy Smokes Smoke Shop
}
```

Таблица выведена из анализа 11+ реальных VAR-листов (май 2026).

### ⚠️ Если встретился неизвестный Chain

> Примечание: при использовании `api-var-by-mid` / `api-var-by-name` (PRIMARY метод через var-list),
> BIN берётся напрямую из API и проблема Unknown Chain **не возникает**.
> Протокол ниже актуален только при ручном использовании устаревшего пути.

CLI вернёт exit code **2** и JSON в stderr:
```json
{
  "event": "UNKNOWN_CHAIN",
  "merchant_name": "...",
  "unknown_chains": ["XXXXXX"],
  "action_required": "..."
}
```

Агент **обязан** выполнить следующие шаги **по порядку**:

---

#### Шаг 1: Запросить var-list через API (PRIMARY)

```bash
merchant api-var-by-mid {MID}
# или
merchant api-var-by-name "{merchant_name}"
```

BIN возвращается напрямую в поле `bin`. Если команда вернула данные → задача решена, перейти к **Шагу 3** чтобы обновить таблицу.

---

#### Шаг 2: Если var-list недоступен — скачать VAR PDF через API

```bash
merchant get-var-by-mid {MID} --save-dir ./tmp/var_learn
# или
merchant get-var-by-merchant-name "{merchant_name}" --save-dir ./tmp/var_learn
```

Если ни var-list, ни var-download не дали результата — запросить PDF у пользователя:

> "Встречен новый Chain: `{chain}` для мерчанта `{merchant_name}`.
> BIN для него неизвестен и не удалось получить VAR автоматически.
> Пожалуйста, пришли VAR-лист (PDF-файл) для этого мерчанта
> или любого другого с Chain `{chain}`."

---

#### Шаг 3: Извлечь BIN и обновить таблицу

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

## Сессия kitdashboard.com (только для лого — VAR сессия не требует)

> ✅ **VAR больше не требует сессии.** `get-var-by-mid` / `get-var-by-merchant-name` и
> `api-var-by-mid` / `api-var-by-name` работают через Bearer токен.
>
> Сессия нужна **только** для команд `upload-logo` / `remove-logo`.

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

> ✅ **Gmail для VAR больше не нужен.** VAR-данные получаются напрямую через
> `GET /terminal/{id}/var-list` (Bearer токен, без проверки почты).

Доступен MCP с инструментами `search_threads` и `get_thread`.

Единственный оставшийся сценарий для Gmail — **2FA код при первом логине**
(нужен только для `upload-logo` / `remove-logo`):
```
# 2FA коды для логина в kitdashboard.com
from:no-reply@kitdashboard.com subject:"verification" newer_than:5m
```

Исторически через Gmail искали уведомления о VAR-листах. **Больше не требуется.**

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

Каждый раз когда агент обрабатывает новый VAR-лист (из API или PDF),
он должен проверить:

1. **Chain уже в таблице?** BIN теперь приходит из `var-list` напрямую, но если встречен
   новый Chain при использовании fallback — добавить в `_CHAIN_TO_BIN` и закоммитить (см. выше).

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
| 2026-05-05 | VAR API refactor: `/terminal/{id}/var-list` — PRIMARY метод (BIN напрямую из JSON); Gmail проверка убрана; сессия нужна только для лого; VarDownloader — legacy fallback |
