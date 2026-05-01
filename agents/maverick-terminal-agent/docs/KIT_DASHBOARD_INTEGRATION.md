# KIT Dashboard API Integration

## Overview

The Maverick Terminal Agent now supports **direct API integration** with KIT Dashboard for fetching VAR (TSYS VAR Sheet) data. This eliminates the need for manual PDF downloads or email lookups.

## Flow: API → PAX Portal

```
┌─────────────────────────────────────┐
│  KIT Dashboard Merchant Data Agent  │
│  (kit-dashboard-merchant-data)      │
└─────────────┬───────────────────────┘
              │
              ▼ API: merchant api-var-by-mid 201100305938
┌─────────────────────────────────────┐
│  KIT Maverick REST API              │
│  /api/merchant/{id}/terminals       │
└─────────────┬───────────────────────┘
              │
              ▼ Returns: VAR data (BIN, Chain, MID, etc.)
┌─────────────────────────────────────┐
│  Maverick Terminal Agent             │
│  PaxProvisioningData.from_api_var()  │
└─────────────┬───────────────────────┘
              │
              ▼ Converts to TSYS form fields
┌─────────────────────────────────────┐
│  PAX Store Portal (paxus.paxstore)  │
│  Terminal Management → Push Task     │
│  → Fill TSYS Parameters              │
└─────────────────────────────────────┘
```

## Key Components

### 1. KIT Dashboard Agent Commands

```bash
cd agents/kit-dashboard-merchant-data

# Get VAR data by Merchant ID (recommended — no browser needed)
merchant api-var-by-mid 201100305938 --json

# Get VAR data by merchant name
merchant api-var-by-name "Pady C Store" --json
```

**Response:** Complete VAR sheet with all TSYS parameters:
```json
[
  {
    "dba": "Pady C Store",
    "mid": "201100305938",
    "chain": "081960",
    "agent_bank": "081960",
    "bin": "422108",
    "store_number": "0002",
    "terminal_number": 7001,
    "city": "Midwest City",
    "state": "Oklahoma",
    "zip": "73110",
    "mcc": "5411",
    "v_number": "V6612507"
  }
]
```

### 2. Convert API Data to PAX Provisioning

```python
from paxstore_provision_from_pdf import PaxProvisioningData

api_var_data = {
    "dba": "Pady C Store",
    "mid": "201100305938",
    "chain": "081960",
    "agent_bank": "081960",
    "bin": "422108",
    "store_number": "0002",
    "terminal_number": 7001,
    "city": "Midwest City",
    "state": "Oklahoma",
    "zip": "73110",
    "mcc": "5411",
    "v_number": "V6612507"
}

data = PaxProvisioningData.from_api_var(api_var_data, serial_number="2290664794")

# Now data contains all fields ready for PAX portal
assert data.terminal_id_number == "76612507"  # V → 7-prefixed
assert data.merchant_display_name == "Pady C Store 201100305938"
```

### 3. Build Provisioning Plan

```python
plan = build_plan_summary(
    data,
    var_source_path="kit-api",  # or "var.pdf" if using PDF
    pdf_path=None,              # None when using API
    pos_device=TerminalDevice("pos", "2630132073", "L1400"),
    pinpad_device=TerminalDevice("pinpad", "2290664794", "A3700"),
    steps={"two-device"},       # or {"merchant", "terminal", "firmware", "tsys"}
    activate_payment_app=False, # Leave TSYS pending
)
```

### 4. Fill TSYS Form in PAX Portal

The `fill_tsys_parameters()` function maps VAR data to PAX form field IDs:

| Field | Input ID | Source |
|-------|----------|--------|
| Merchant Name | `6_tsys_F1_tsys_param_merchantName` | VAR DBA |
| BIN | `0_tsys_F1_tsys_param_BIN` | API `bin` |
| Agent Bank | `1_tsys_F1_tsys_param_agentNumber` | API `agent_bank` |
| Chain | `2_tsys_F1_tsys_param_chainNumber` | API `chain` |
| Merchant # | `3_tsys_F1_tsys_param_MID` | API `mid` |
| Store # | `4_tsys_F1_tsys_param_storeNumber` | API `store_number` |
| Terminal # | `5_tsys_F1_tsys_param_terminalNumber` | API `terminal_number` |
| City | `7_tsys_F1_tsys_param_merchantCity` | API `city` |
| State | `8_tsys_F1_tsys_param_merchantState` | API `state` |
| ZIP | `9_tsys_F1_tsys_param_cityCode` | API `zip` |
| MCC | `13_tsys_F1_tsys_param_categoryCode` | API `mcc` |
| Terminal ID # | `19_tsys_F1_tsys_param_TID` | Derived: `V6612507` → `76612507` |

## Chain → BIN Mapping

BIN (Bank Identification Number) is derived from Chain value via lookup table:

```python
_CHAIN_TO_BIN = {
    "081960": "422108",   # FFB Bank (majority of merchants)
    "261960": "442114",   # e.g., Ali Baba Smoke and Gift Shop
    "051960": "403982",   # e.g., Holy Smokes Smoke Shop
}
```

**If you encounter an unknown Chain:**
1. Run `merchant get-var-by-merchant-name "{name}"` to download PDF
2. Extract BIN and Chain from PDF
3. Add mapping to `kit-dashboard-merchant-data/src/merchant_data/models.py`
4. Run tests again

See `AGENT_CONTEXT.md` in kit-dashboard-merchant-data for full protocol.

## Terminal ID Number Derivation

V Number from API is converted to Terminal ID Number (TID) for TSYS:

```python
def derive_terminal_id_number(v_number: str) -> str:
    # V6612507 → 76612507 (prepend 7)
    if v_number.startswith("V") and len(v_number) > 1:
        return "7" + v_number[1:]
    if v_number and not v_number.startswith("7"):
        return "7" + v_number
    return v_number
```

## Two-Device Workflow Rules

For POS + PIN pad provisioning:

### POS Device (e.g., L1400)
1. Latest Firmware
2. KIT Stock (app)
3. KIT Merchant (app)
4. KIT POS (app) — usually auto-installed

### PIN Pad Device (e.g., A3700)
1. Latest Firmware
2. **KIT Back Screen** (if model supports it) — A3700 ✓, A35 ✗
3. **BroadPOS TSYS Sierra** (payment processing app)
   - Uses `Parameter File:retail.zip`
   - Fills TSYS parameters from VAR
   - **Stays PENDING** unless `--activate-payment-app` is passed

## API Advantages over PDF

| Method | Speed | Browser | Auth | Multi-terminal |
|--------|-------|---------|------|-----------------|
| **API** | Instant | ✗ | Bearer token | Multiple rows |
| PDF | Slow | ✓ | Session cookie | Single download |

## Testing

```bash
cd agents/maverick-terminal-agent

# Run all tests (14 tests total)
pytest tests/ -v

# Run only KIT Dashboard integration tests
pytest tests/test_kit_dashboard_integration.py -v

# Run specific test
pytest tests/test_kit_dashboard_integration.py::TestKitDashboardIntegration::test_pady_c_store_api_data_to_pax_provisioning -v
```

## Example: Pady C Store (MID: 201100305938)

**Scenario:** Provision two devices for Pady C Store:
- POS: L1400 (SN: 2630132073)
- PIN pad: A3700 (SN: 2290664794)

### Step 1: Get VAR data from API

```bash
cd agents/kit-dashboard-merchant-data
merchant api-var-by-mid 201100305938 --json
```

Returns 3 terminals; select the one for SN 2290664794:
- V Number: V6612507
- Terminal #: 7001
- Store #: 0002

### Step 2: Convert to PAX data

```python
api_var = {...}  # From API
data = PaxProvisioningData.from_api_var(api_var, serial_number="2290664794")
```

### Step 3: Build plan

```python
plan = build_plan_summary(
    data,
    var_source_path="kit-api",
    pdf_path=None,
    pos_device=TerminalDevice("pos", "2630132073", "L1400"),
    pinpad_device=TerminalDevice("pinpad", "2290664794", "A3700"),
    steps={"two-device"},
    activate_payment_app=False
)
```

### Step 4: Execute in PAX portal (manual or via Playwright)

- Login → Terminal Management
- Select Pady C Store merchant
- Create POS terminal (L1400)
- Create PIN pad terminal (A3700)
- Push Firmware to both
- Push Apps:
  - POS: KIT Stock + KIT Merchant
  - PIN pad: KIT Back Screen + BroadPOS TSYS Sierra
- Fill TSYS form with API-derived parameters
- Leave BroadPOS TSYS Sierra **PENDING**

## Error Handling

### Unknown Chain

If API returns a Chain not in the lookup table:

```
{ "event": "UNKNOWN_CHAIN", "merchant_name": "...", "unknown_chains": ["XXXXXX"] }
```

**Action:** See AGENT_CONTEXT.md for recovery protocol.

### Missing VAR Data

If merchant has no terminals in API:

- Try `merchant get-var-by-merchant-name "{name}"` to download PDF
- Search Gmail for VAR notification: `from:no-reply@kitdashboard.com subject:"VAR available" "{merchant_name}"`
- Ask user for VAR file

## References

- **KIT Dashboard Merchant Data Agent:** `agents/kit-dashboard-merchant-data/AGENT_CONTEXT.md`
- **PAX Store Recorded Flow:** `docs/PAXSTORE_RECORDED_FLOW.md`
- **Tests:** `tests/test_kit_dashboard_integration.py`
- **Script:** `scripts/paxstore_provision_from_pdf.py`
