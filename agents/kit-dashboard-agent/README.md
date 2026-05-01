# KIT Dashboard Agent

Automated merchant onboarding agent for KIT Dashboard.

**Primary mode: REST API** — no browser required for merchant lookup or application creation.  
Browser automation remains available as a fallback for edge cases.

---

## What This Agent Does

1. **Look up merchants** — by name, MID, or internal ID via KIT Dashboard API
2. **Get VAR sheet data** — all terminal fields (BIN, chain, MCC, store #, etc.) via API
3. **Create boarding applications** — full merchant onboarding via the Boarding Application API
4. **Validate applications** — check required fields before submission
5. **Parse merchant documents** — PDFs, driver licenses, bank checks (OCR/MICR)
6. **Fill KIT Dashboard forms** — Playwright browser automation (fallback)

---

## Data Source Priority

```
KIT Dashboard REST API  ←── primary (instant, no browser, no session)
       ↓ (if API unavailable or data missing)
Document parsing (PDF / driver license / check image)
       ↓ (if no documents)
Browser automation (Playwright, kitdashboard.com)
```

---

## Installation

```bash
pip install -e .

# Optional: OCR support for document parsing
pip install -e '.[ocr]'

# Optional: browser automation fallback
pip install -e '.[browser]'
playwright install chromium
```

## Configuration

Create a `.env` file:

```bash
# Required for API mode (primary)
KIT_API_KEY=your-api-key

# Required for browser fallback only
KIT_DASHBOARD_EMAIL=your-email@example.com
KIT_DASHBOARD_PASSWORD=your-password
KIT_DASHBOARD_URL=https://kitdashboard.com/
```

Get your API key at: https://kitdashboard.com → Settings → Developers

---

## Usage

### Merchant Lookup (API)

```bash
# Look up by name
kit-merchant api-by-name "El Camino Mart"

# Look up by MID
kit-merchant api-by-mid 201100300996

# Get full VAR sheet data (terminal BIN, chain, MCC, etc.)
kit-merchant api-var-by-mid 201100305938
kit-merchant api-var-by-name "Pady C Store"

# JSON output
kit-merchant api-var-by-mid 201100305938 --json
```

### Merchant Onboarding (API)

```bash
# Search MCC code by keyword or number
kit-merchant board-mcc-search "grocery"
kit-merchant board-mcc-search "5411"

# Create a new boarding application (fully populated in one call)
kit-merchant board-create \
  --legal-name "Sky Blue Store LLC" \
  --dba "Sky Blue Store" \
  --entity-type "LLC" \
  --ein "123456789" \
  --founded "2020-01-01" \
  --mcc-id 702 \
  --description "Convenience grocery store" \
  --street "4500 W Century Blvd" --city "Inglewood" --state "California" --zip "90304" \
  --phone "+1 310-555-0100" --email "owner@gmail.com" \
  --principal-first "Maria" --principal-last "Gonzalez" \
  --principal-title "Owner" \
  --principal-ssn "123-45-6789" --principal-dob "1980-01-15" \
  --principal-email "maria@gmail.com" --principal-phone "+1 310-555-0100" \
  --principal-street "100 Oak Ave" --principal-city "Inglewood" \
  --principal-state "California" --principal-zip "90301" \
  --monthly-volume 50000 --avg-tx 50 --max-tx 500 \
  --routing "021000021" --account "1234567890"

# Validate (check remaining required fields)
kit-merchant board-validate 756692

# List recent applications
kit-merchant board-list --limit 10

# Get full application details
kit-merchant board-get 756692
```

### Boarding Process (API)

```
1. board-mcc-search     → find correct MCC id for the business type
2. board-create         → POST skeleton + PUT all fields in one call → returns app_id
3. board-validate       → confirm no missing fields
4. board-get --json     → inspect full application object
5. (manual) Submit for underwriting via kitdashboard.com
```

### Document Parsing (offline)

```bash
# Parse merchant application PDF + supporting docs
kit parse-docs application.pdf check.jpg license.jpg

# Build onboarding plan from documents
kit plan application.pdf check.jpg license.jpg

# Generate formatted report
kit report application.pdf check.jpg license.jpg
```

---

## API Reference

Base URL: `https://dashboard.maverickpayments.com/api`  
Auth: `Authorization: Bearer <KIT_API_KEY>`

Key endpoints used by this agent:

| Endpoint | Description |
|----------|-------------|
| `GET /merchant` | List/search merchants |
| `GET /boarding-application` | List boarding applications |
| `POST /boarding-application/create` | Create new application |
| `PUT /boarding-application/<id>` | Fill all sections |
| `GET /boarding-application/<id>/validate` | Validate — returns errors dict |
| `GET /boarding-application/<id>/url` | Get merchant-facing form link |
| `PUT /boarding-application/<id>/status/Underwriting` | Submit for approval |
| `GET /boarding-application/mcc` | Search MCC codes |
| `GET /terminal/<id>/var-download` | Download VAR PDF |
| `GET /reporting/authorizations/<dbaId>` | Transaction reporting |

Full endpoint reference: `agents/kit-dashboard-merchant-data` package → `MerchantAPIService`, `MerchantOnboardingService`

---

## Project Structure

```
kit-dashboard-agent/
├── src/kit_agent/
│   ├── cli.py                    # CLI entry point
│   ├── models.py                 # KitMerchantProfile, KitOnboardingPlan, etc.
│   ├── kit_orchestrator.py       # Onboarding workflow coordinator
│   ├── services/
│   │   └── kit_dashboard.py      # Browser automation (Playwright, fallback)
│   └── parsers/
│       ├── kit_documents.py      # PDF / image document parser
│       └── ocr_micr.py           # OCR + MICR bank check recognition
├── tests/
├── config/
└── pyproject.toml

# API services live in the sibling package:
agents/kit-dashboard-merchant-data/src/merchant_data/
├── services/
│   ├── kit_api.py            # MerchantAPIService — lookup, VAR data
│   ├── kit_onboarding.py     # MerchantOnboardingService — create/fill boarding apps
│   └── kit_var_downloader.py # HTTP session VAR PDF download
└── models.py                 # VarData, NewMerchantProfile, OnboardingResult, etc.
```

---

## Supported Documents (for parsing mode)

- **PDF** — merchant application forms, voided checks
- **JPEG/PNG** — driver licenses, green cards, check images
- **OCR** — EasyOCR with Tesseract fallback
- **MICR** — bank routing/account number extraction from checks

---

## Security

- Sensitive data (SSN, account numbers) masked by default in CLI output
- Credentials from `.env` only — no hardcoded secrets
- ABA routing number validation before submission
- API key separate from dashboard login credentials
