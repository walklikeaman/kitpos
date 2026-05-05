# VAR Sheet API Integration Guide

## Что изменилось

Ранее VAR данные для мерчантов получались только из PDF файлов (парсинг через `VarPdfParser`).  
Теперь доступны два прямых REST API эндпоинта, которые работают с обычным Bearer токеном — без логина, без сессионных cookie, без браузера.

---

## API эндпоинты

**Base URL:** `https://dashboard.maverickpayments.com/api`  
**Auth:** `Authorization: Bearer <KIT_API_KEY>`  
**Docs:** https://developers.kitdashboard.com/#/dashboard  
**GitHub репозиторий:** https://github.com/walklikeaman/kitpos

| Метод | Путь | Что возвращает |
|-------|------|----------------|
| `GET` | `/terminal/{terminal_id}/var-list` | JSON со всеми VAR полями |
| `GET` | `/terminal/{terminal_id}/var-download` | PDF файл (VAR Sheet) |

> ⚠️ `terminal_id` — это **внутренний ID терминала** (например `812330`), НЕ TID (7000) и НЕ V-номер (V6592346).  
> Получить список терминалов мерчанта: `GET /terminal?filter[merchant.id][eq]={merchant_internal_id}`

---

## Пример ответа `/terminal/{id}/var-list`

```json
{
  "id": 812330,
  "dba": { "id": 345680, "name": "Snack Zone" },
  "merchant": { "id": 303608, "name": "Snack Zone Inc" },
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
  "equipment": {
    "providedBy": "ISO",
    "equipmentType": "NoHardware",
    "used": "KIT POS",
    "discountPeriod": "Daily",
    "fundingPeriod": "SameDay"
  }
}
```

---

## Уже реализовано (референс)

**Файл:** `agents/kit-dashboard-merchant-data/src/merchant_data/services/kit_api.py`  
**Класс:** `MerchantAPIService`  
**Коммит:** `6b69838`

```python
def var_json_by_terminal_id(self, terminal_id: int | str) -> dict:
    """Возвращает полные VAR данные как JSON.
    GET /terminal/<id>/var-list — работает с Bearer токеном.
    """
    return self._get(f"/terminal/{terminal_id}/var-list", {})

def var_pdf_by_terminal_id(self, terminal_id: int | str, save_dir: Path) -> Path:
    """Скачивает VAR PDF файл.
    GET /terminal/<id>/var-download — работает с Bearer токеном.
    Возвращает путь к сохранённому PDF.
    """
    ...
```

Вспомогательный метод `_get` в том же классе:

```python
def _get(self, path: str, params: dict) -> dict:
    url = f"https://dashboard.maverickpayments.com/api{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {self.api_key}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://kitdashboard.com/",
        "Origin": "https://kitdashboard.com",
    })
    with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
        return json.loads(resp.read().decode())
```

---

## Что нужно сделать в `maverick-terminal-agent`

### Цель
Добавить возможность получать VAR данные через API (без PDF) как первый приоритет.  
Текущий PDF-флоу оставить как fallback.

### Приоритет данных после изменений
```
KIT Dashboard API (/terminal/{id}/var-list)   ← НОВЫЙ ПРИОРИТЕТ 1
        ↓ (если нет KIT_API_KEY или API недоступен)
Email inbox → PDF attachment                  ← приоритет 2 (текущий)
        ↓ (если нет письма)
Ручная передача PDF файла                     ← приоритет 3 (текущий)
```

### Шаг 1 — Создать `services/kit_var_api.py`

Файл: `agents/maverick-terminal-agent/src/maverick_agent/services/kit_var_api.py`

```python
"""
KIT Dashboard VAR API client.

Endpoints (no login, Bearer token only):
  GET /terminal/{id}/var-list      → JSON with all VAR fields
  GET /terminal/{id}/var-download  → PDF file

terminal_id — internal API id (e.g. 812330), NOT tid (7000) or V-number.
Get terminal list: GET /terminal?filter[merchant.id][eq]={merchant_id}
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_BASE = "https://dashboard.maverickpayments.com/api"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _ssl_ctx() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


_SSL = _ssl_ctx()
_HEADERS = lambda key: {
    "Authorization": f"Bearer {key}",
    "Accept": "application/json",
    "User-Agent": _UA,
    "Referer": "https://kitdashboard.com/",
    "Origin": "https://kitdashboard.com",
}


class KitVarApiClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def get_terminals_for_merchant(self, merchant_id: int | str) -> list[dict]:
        """Return list of terminals for a merchant by internal merchant id."""
        data = self._get("/terminal", {"filter[merchant.id][eq]": merchant_id, "per-page": 50})
        return data.get("items", [])

    def var_json(self, terminal_id: int | str) -> dict:
        """Return full VAR data as JSON for a terminal."""
        return self._get(f"/terminal/{terminal_id}/var-list", {})

    def var_pdf(self, terminal_id: int | str, save_dir: Path) -> Path:
        """Download VAR PDF. Returns path to saved file."""
        import re
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        url = f"{_BASE}/terminal/{terminal_id}/var-download"
        req = urllib.request.Request(url, headers={
            **_HEADERS(self.api_key),
            "Accept": "application/pdf,*/*",
        })
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
                data = resp.read()
                cd = resp.headers.get("Content-Disposition", "")
                fname_m = re.search(r'filename="([^"]+)"', cd)
                fname = fname_m.group(1) if fname_m else f"terminal-{terminal_id}-VAR.pdf"
                dest = save_dir / fname
                dest.write_bytes(data)
                return dest
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"var-download HTTP {exc.code}: {exc.read().decode()}") from exc

    def find_terminal_by_merchant_number(self, merchant_number: str | int) -> dict | None:
        """
        Find terminal by 12-digit MID (merchantNumber field).
        Scans all merchants page by page — slow but reliable.
        """
        mid_int = int(merchant_number)
        page = 1
        while True:
            data = self._get("/merchant", {"per-page": 50, "page": page})
            for item in data.get("items", []):
                for dba in item.get("dbas", []):
                    proc = dba.get("processing") or {}
                    if proc.get("mid") == mid_int:
                        terminals = self.get_terminals_for_merchant(item["id"])
                        return terminals[0] if terminals else None
            meta = data.get("_meta", {})
            if page >= meta.get("pageCount", 1):
                break
            page += 1
        return None

    def _get(self, path: str, params: dict) -> dict:
        qs = urllib.parse.urlencode(params)
        url = f"{_BASE}{path}{'?' + qs if qs else ''}"
        req = urllib.request.Request(url, headers=_HEADERS(self.api_key))
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"API {exc.code}: {exc.read().decode()}") from exc
```

### Шаг 2 — Обновить `orchestrator.py`

В начале файла добавить импорт:
```python
from maverick_agent.services.kit_var_api import KitVarApiClient
```

В `ProvisioningOrchestrator` добавить поле:
```python
kit_api_client: KitVarApiClient | None = None
```

В методе `build_plan` добавить API-ветку **перед** блоком с PDF:

```python
def build_plan(self, request: MerchantRequest) -> RunOutcome:
    pdf_path = request.pdf_path
    notes: list[str] = []

    # ── Приоритет 1: KIT Dashboard API ───────────────────────────────────
    if self.kit_api_client is not None and request.merchant_number:
        try:
            terminal = self.kit_api_client.find_terminal_by_merchant_number(
                request.merchant_number
            )
            if terminal:
                terminal_id = terminal["id"]
                var_data = self.kit_api_client.var_json(terminal_id)
                notes.append(f"VAR data loaded from KIT API (terminal_id={terminal_id})")
                # Конвертировать var_data → extracted dict и вернуть план
                extracted = _var_json_to_extracted(var_data)
                return self._build_outcome_from_extracted(request, extracted, notes)
        except Exception as exc:
            notes.append(f"KIT API unavailable ({exc}), falling back to PDF")

    # ── Приоритет 2: Email inbox PDF ─────────────────────────────────────
    # ... (существующий код)
```

### Шаг 3 — Добавить конвертер `_var_json_to_extracted`

```python
def _var_json_to_extracted(var_data: dict) -> dict:
    """Convert /terminal/{id}/var-list response to extracted fields dict."""
    addr = var_data.get("address") or {}
    return {
        "dba_name":            (var_data.get("dba") or {}).get("name", ""),
        "merchant_number":     str(var_data.get("merchantNumber", "")),
        "bin":                 var_data.get("bin", ""),
        "chain":               var_data.get("chain", ""),
        "agent_bank":          var_data.get("agentBank", ""),
        "mcc":                 str(var_data.get("mcc", "")),
        "store_number":        var_data.get("storeNumber", ""),
        "terminal_number":     str(var_data.get("tid", "")),
        "location_number":     var_data.get("locationNumber", ""),
        "state":               addr.get("state", ""),
        "city":                addr.get("city", ""),
        "zip":                 addr.get("zip", ""),
        "street":              addr.get("streetAddress", ""),
        "phone":               var_data.get("customerServicePhone", ""),
        "approved_monthly_volume": var_data.get("approvedMonthlyVolume", ""),
    }
```

### Шаг 4 — Инициализировать клиент в `cli.py`

Найти место где создаётся `ProvisioningOrchestrator` и добавить:

```python
from maverick_agent.services.kit_var_api import KitVarApiClient

kit_client = KitVarApiClient(settings.kit_api_key) if settings.kit_api_key else None

orchestrator = ProvisioningOrchestrator(
    parser=VarPdfParser(...),
    inbox_client=inbox_client,
    kit_api_client=kit_client,   # ← добавить
)
```

---

## Переменная окружения

В `.env` файле агента убедиться, что есть:

```bash
KIT_API_KEY=kjQ0.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

`kit_api_key` уже прописан в `config.py` (`os.getenv("KIT_API_KEY")`), так что дополнительных изменений в конфиге не нужно.

---

## Полезные ссылки

| Ресурс | Ссылка |
|--------|--------|
| GitHub репозиторий | https://github.com/walklikeaman/kitpos |
| Референс реализация | `agents/kit-dashboard-merchant-data/src/merchant_data/services/kit_api.py` |
| KIT API документация | https://developers.kitdashboard.com/#/dashboard |
| Raw docs (markdown) | https://developers.kitdashboard.com/dashboard.md |
| KIT Dashboard UI | https://kitdashboard.com |
| API Base URL | `https://dashboard.maverickpayments.com/api` |
| Подтверждённые эндпоинты | `GET /terminal/{id}/var-list`, `GET /terminal/{id}/var-download` |
