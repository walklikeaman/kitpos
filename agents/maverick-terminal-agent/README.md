# Maverick Terminal Agent

Automated terminal provisioning agent for adding payment terminals to merchants.

## Features

- Parse merchant VAR PDFs
- Resolve merchant VAR data from KIT Dashboard API when `KIT_API_KEY` is available
- Extract VAR numbers and TSYS parameter values
- Auto-detect merchant data from email inbox (IMAP)
- Build provisioning plans for PAX terminals
- Validate merchant references and required fields

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/maverick-terminal-agent.git
cd maverick-terminal-agent

# Install dependencies
pip install -e .

# Optional: Install with OCR support for serial number recognition
pip install -e '.[ocr]'
```

## Configuration

Create a `.env` file with:

```bash
# Email configuration (optional)
MAIL_PROVIDER=imap
MAIL_IMAP_HOST=mail.example.com
MAIL_IMAP_PORT=993
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-password
MAIL_IMAP_MAILBOX=INBOX
MAIL_SCAN_LIMIT=50

# KIT Dashboard API lookup (preferred for VAR data)
KIT_API_KEY=your-kit-api-key
```

Or set environment variables:

```bash
export MAIL_IMAP_HOST="mail.example.com"
export MAIL_IMAP_PORT="993"
export MAIL_USERNAME="your-email"
export MAIL_PASSWORD="your-password"
```

## Usage

### Parse a VAR PDF

```bash
maverick parse-pdf "/path/to/merchant-vat.pdf"
```

### Build a provisioning plan

```bash
maverick plan \
  --merchant-number 201100302455 \
  --serial-number ABC123DEF456 \
  --pdf "/path/to/merchant-vat.pdf"
```

Or auto-detect PDF from email:

```bash
maverick plan \
  --merchant-number 201100302455 \
  --serial-number ABC123DEF456
```

### Run the PAX Store browser workflow

Install browser support:

```bash
pip install -e '.[browser]'
python -m playwright install chromium
```

Dry-run the recorded browser flow. This fills forms and writes screenshots under
`tmp/screenshots/`, but does not click final submit buttons:

```bash
python scripts/paxstore_provision_from_pdf.py \
  --pdf "/path/to/merchant-var.pdf" \
  --serial-number 2290653126 \
  --steps merchant,terminal
```

Execute submit clicks explicitly:

```bash
python scripts/paxstore_provision_from_pdf.py \
  --pdf "/path/to/merchant-var.pdf" \
  --serial-number 2290653126 \
  --steps merchant,terminal \
  --submit
```

Two-device merchant flow. The runner resolves VAR data from the KIT Dashboard
API first when `KIT_API_KEY` is configured, then falls back to Kit Dashboard PDF
download and email when configured:

```bash
python scripts/paxstore_provision_from_pdf.py \
  --merchant-number 201100306001 \
  --var-source kit-api \
  --var-v-number V6615476 \
  --pos-serial 2630132073 \
  --pinpad-serial 2620079273 \
  --pos-model L1400 \
  --pinpad-model A3700 \
  --steps two-device \
  --plan-only
```

Rules in this flow:

- POS gets latest firmware first, then `KIT Stock` and `KIT Merchant`; `KIT POS` is expected to be automatic.
- PIN pad gets latest firmware first, then `BroadPOS TSYS Sierra`.
- `KIT Back Screen` is installed only for supported PIN pad models, currently `A3700`/`3700`; use `--pinpad-back-screen` or `--no-pinpad-back-screen` to override.
- BroadPOS TSYS Sierra is installed **via Push Template** (Push App dialog → Push Template tab → tick template → OK). Do not search the app catalog by hand. The chosen template loads its parameter file (e.g. `retail.zip`) automatically.
- TSYS parameters are filled from VAR; the push stays Pending unless `--activate-payment-app` is explicitly passed.
- If a merchant has multiple VAR rows, select the intended row with `--var-v-number` or `--var-terminal-number`; otherwise the first API row is used.

**Strict provisioning rules:** see [`docs/PAXSTORE_PROVISIONING_RULES.md`](docs/PAXSTORE_PROVISIONING_RULES.md). Highlights:

- Merchant creation: only `Name = "{DBA} {MID}"`; no address / phone / state / city / merchant type.
- Terminal creation: type SN first; Model auto-detects — do not pick it manually.
- App install: Push Template (not a manual search for BroadPOS TSYS Sierra).
- Don't change the Model dropdown in the BroadPOS App Detail panel.

The PAX Store runner reads Merchant Number and TSYS parameter values from KIT API
or VAR PDF, then fills the recorded browser flow. See
`docs/PAXSTORE_RECORDED_FLOW.md` for the TSYS field mapping extracted from the
browser recording.

Every run appends a non-secret JSONL record to
`tmp/run-history/paxstore_runs.jsonl`. Use it to compare successful and failed
runs by mode (`headless`/`headed`), steps, device models, serial numbers,
submit flags, VAR source path, PDF path when used, and final error/status.
Screenshots and page text remain under `tmp/screenshots/`.

## Project Structure

```
maverick-terminal-agent/
├── src/maverick_agent/
│   ├── cli.py                    # Command-line interface
│   ├── config.py                 # Configuration management
│   ├── models.py                 # Data models
│   ├── orchestrator.py           # Provisioning orchestrator
│   ├── services/
│   │   ├── paxstore.py          # PAX Store integration
│   │   └── inbox.py             # Email inbox client
│   └── parsers/
│       └── var_pdf.py           # VAR PDF parser
├── tests/                        # Unit tests
├── pyproject.toml               # Project configuration
└── README.md
```

## Architecture

1. **CLI** - Command interface for operators
2. **ProvisioningOrchestrator** - Coordinates the provisioning workflow
3. **VarPdfParser** - Extracts data from merchant PDFs
4. **ImapInboxClient** - Auto-detects merchant PDFs in email
5. **PAXStore** - Integration with payment processor

## Models

- `MerchantRequest` - Input: merchant number, serial number, PDF path
- `VarPayload` - Extracted fields from PDF
- `RunPlan` - Provisioning plan with validated fields
- `RunOutcome` - Final status and next actions
