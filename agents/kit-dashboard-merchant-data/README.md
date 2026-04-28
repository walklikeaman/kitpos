# KIT Dashboard Merchant Data Agent

Headless browser agent that logs into **kitdashboard.com** and extracts merchant data (principal name, phone, email, business address) and downloads VAR PDF files — by **Merchant ID (MID)** or **merchant name**.

## What it does

| Command | Input | Output |
|---|---|---|
| `merchant by-id` | MID (e.g. `201100300996`) | Principal name, phone, email |
| `merchant by-name` | Name (e.g. `"El Camino"`) | Principal name, phone, email |
| `merchant get-var-by-id` | MID | Downloads VAR PDF to `./downloads/` |
| `merchant get-var-by-name` | Name | Downloads VAR PDF to `./downloads/` |

## Installation

```bash
cd agents/kit-dashboard-merchant-data
pip install -e .
playwright install chromium
```

## Configuration

```bash
cp .env.example .env
# fill in KIT_EMAIL and KIT_PASSWORD
```

> **Session caching**: after the first successful login the browser session is saved to `tmp/kit-merchant-state.json`. Subsequent runs reuse the session — no login required until it expires.

> **2FA**: if triggered, the agent writes `tmp/2fa_requested.txt` and polls `tmp/2fa_code.txt` for 90 seconds. Write the 6-digit code there and it continues automatically.

## Usage

### Look up merchant by MID
```bash
merchant by-id 201100300996
```
```
Merchant:   El Camino Mart Inc
ID:         201100300996
Principal:  Ali Alomari
Phone:      +1 510-200-2944
Email:      alialomariusa@gmail.com
Profile:    https://kitdashboard.com/merchant/profile/index?id=299390
```

### Look up merchant by name
```bash
merchant by-name "El Camino"
```

### Download VAR file by MID
```bash
merchant get-var-by-id 201100300996
```
```
Merchant:   El Camino Mart Inc
Search:     201100300996
Profile:    https://kitdashboard.com/merchant/profile/index?id=299390
VAR file:   downloads/El-Camino-Mart-KIT-POSVAR-Sheet.pdf
```

### Download VAR file by name
```bash
merchant get-var-by-name "El Camino"
```

### JSON output
```bash
merchant by-id 201100300996 --json
```

### Debug mode (saves screenshots + page text)
```bash
merchant by-id 201100300996 --debug
```

### Pass 2FA code manually
```bash
merchant by-id 201100300996 --verification-code 123456
```

## How the headless browser works

1. **Session reuse** — loads `tmp/kit-merchant-state.json` as Playwright `storage_state` (cookies). If valid, login is skipped.

2. **Login flow** (when session is expired):
   - Navigate to `https://kitdashboard.com/`
   - Fill email + password, click "Sign in"
   - Check for 2FA prompt

3. **2FA handling**:
   - Writes `tmp/2fa_requested.txt`, polls `tmp/2fa_code.txt` every 2s (90s timeout)
   - Write the code to `tmp/2fa_code.txt` from any external process

4. **Merchant search**:
   - Navigate to `https://kitdashboard.com/merchant/default/index`
   - Open Filters → fill `#merchantsearch-searchterm` → Apply
   - For 12-digit MID: find the card containing that MID, navigate directly to its profile URL
   - For name: click first result link

5. **Data extraction** from `body.inner_text()`:
   - Principal: regex after `Principal` label (skips numeric ID prefix like `326960 Name`)
   - Phone: first phone pattern after `Phone` label
   - Email: text after `Contact Email address` label
   - MID: regex `20110\d{7}` in body

6. **VAR download**:
   - Scans `<a href>` tags for VAR/PDF links
   - Falls back to positional CSS `div:nth-of-type(7) > div > div:nth-of-type(2) a`
   - Uses `page.expect_download()` → saves to `./downloads/`

## Project structure

```
kit-dashboard-merchant-data/
├── .env.example
├── pyproject.toml
├── AGENT_CONTEXT.md          ← detailed notes for AI agents
└── src/merchant_data/
    ├── cli.py                ← Typer CLI entrypoints
    ├── models.py             ← KitCredentials, MerchantResult, VarDownloadResult
    └── services/
        └── kit_merchant_lookup.py   ← all browser automation logic
```

## Tested successfully (2026-04-28)

| MID | Merchant | Principal | Phone |
|---|---|---|---|
| 201100300996 | El Camino Mart Inc | Ali Alomari | +1 510-200-2944 |
| 201100306001 | B&B CHILL AND BLEND | Blal Alshohatee | +1 510-529-8377 |
| 201100305938 | PADY C STORE LLC | Abdulfattah Pady | +1 615-429-2561 |
| 50110092643 | Hesham Al Wahaini (VAR only) | — | — |
