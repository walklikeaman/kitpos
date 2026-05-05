# Maverick Terminal Agent

Automated PAX Store provisioning agent — creates merchants and terminals, pushes firmware, installs BroadPOS TSYS Sierra via Push Template, fills TSYS parameters.

## VAR Data Source Priority

```
1. KIT Dashboard API   ← PRIMARY (no browser, no PDF, Bearer token only)
2. VAR PDF             ← fallback (user provides file manually)
3. Email inbox (IMAP)  ← last resort only
```

**Always use the API first.** PDF and email are fallbacks for edge cases.

See [`docs/var-api-integration-guide.md`](docs/var-api-integration-guide.md) for API endpoints and implementation reference.

## Configuration

Create `.env` in the agent folder:

```bash
# KIT Dashboard API — PRIMARY VAR source
KIT_API_KEY=your-kit-api-key

# PAX Store credentials (can also use PAX_USERNAME / PAX_PASSWORD env vars)
# PAX_USERNAME=nikita@kit-pos.com
# PAX_PASSWORD=...

# Email inbox — only needed as last-resort fallback
# MAIL_PROVIDER=imap
# MAIL_IMAP_HOST=mail.example.com
# MAIL_IMAP_PORT=993
# MAIL_USERNAME=your-email@example.com
# MAIL_PASSWORD=your-password
```

## Installation

```bash
cd agents/maverick-terminal-agent
pip install -e '.[browser]'
python -m playwright install chromium
```

## Running "Build the File" (standard provisioning)

### Single device (PIN pad)

```bash
python3 scripts/paxstore_provision_from_pdf.py \
  --merchant-number 201100305938 \
  --var-source kit-api \
  --pinpad-serial 2290664794 \
  --pinpad-model A3700 \
  --steps two-device \
  --submit
```

### Two devices (POS + PIN pad)

```bash
python3 scripts/paxstore_provision_from_pdf.py \
  --merchant-number 201100306001 \
  --var-source kit-api \
  --pos-serial 2630132073 \
  --pinpad-serial 2620079273 \
  --pos-model L1400 \
  --pinpad-model A3700 \
  --steps two-device \
  --submit
```

### Dry-run (plan only, no changes)

```bash
python3 scripts/paxstore_provision_from_pdf.py \
  --merchant-number 201100305938 \
  --var-source kit-api \
  --pinpad-serial 2290664794 \
  --pinpad-model A3700 \
  --steps two-device \
  --plan-only
```

### Fallback: VAR PDF provided manually

```bash
python3 scripts/paxstore_provision_from_pdf.py \
  --pdf "/path/to/merchant-var.pdf" \
  --pinpad-serial 2290664794 \
  --pinpad-model A3700 \
  --steps two-device \
  --submit
```

## Key flags

| Flag | Default | Description |
|------|---------|-------------|
| `--var-source kit-api` | — | Fetch VAR from KIT Dashboard API (primary) |
| `--var-v-number V6612507` | first row | Pick specific VAR row by V Number |
| `--var-terminal-number 7001` | first row | Pick specific VAR row by terminal number |
| `--submit` | off | Click final OK/NEXT buttons (make changes) |
| `--plan-only` | off | Print plan, don't open PAX Store |
| `--headed` | off | Show browser window (debug only) |
| `--activate-payment-app` | off | Activate BroadPOS after filling TSYS |

## Browser mode

**Default: headless.** Chrome does not open visually. Use `--headed` only for debugging.

## Strict Provisioning Rules

See [`docs/PAXSTORE_PROVISIONING_RULES.md`](docs/PAXSTORE_PROVISIONING_RULES.md). Key points:

- **VAR source: KIT API first.** Only fall back to PDF if API is unavailable.
- **VAR row: first row by default.** Use `--var-v-number` only when explicitly told.
- **Check run history before provisioning.** Grep `tmp/run-history/paxstore_runs.jsonl` for the serial number — if `success + submit: true` exists, confirm with user first.
- **Browser: headless by default.** Use `--headed` for debugging only.
- Merchant creation: `Name = "{DBA} {MID}"` only. No address, phone, state, city.
- Terminal creation: enter SN first — Model auto-detects.
- App install: Push Template only (do not search for BroadPOS manually).
- Do not touch the Model dropdown in App Detail.
- After provisioning: upload merchant logo via `merchant upload-logo logo.png --mid <MID>`.

## Run History

Every run is logged to `tmp/run-history/paxstore_runs.jsonl`.

```bash
# Check if a serial was already provisioned
grep "2290664794" tmp/run-history/paxstore_runs.jsonl | python3 -c "
import sys, json
for l in sys.stdin:
    r = json.loads(l)
    print(r['timestamp_utc'][:16], r['status'], 'submit=' + str(r.get('submit')), r.get('pinpad_serial',''))
"
```

## Project Structure

```
maverick-terminal-agent/
├── src/maverick_agent/
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── orchestrator.py
│   ├── services/
│   │   ├── kit_var_api.py   # KIT Dashboard VAR API client (primary)
│   │   ├── paxstore.py      # PAX Store browser automation
│   │   └── inbox.py         # Email inbox (fallback only)
│   └── parsers/
│       └── var_pdf.py       # VAR PDF parser (fallback only)
├── docs/
│   ├── PAXSTORE_PROVISIONING_RULES.md   # Authoritative rules
│   ├── var-api-integration-guide.md     # VAR API technical reference
│   └── KIT_DASHBOARD_INTEGRATION.md
├── scripts/
│   ├── paxstore_provision_from_pdf.py   # Main provisioning script
│   └── install_via_push_template.py
├── tmp/
│   ├── run-history/paxstore_runs.jsonl  # Run log
│   └── screenshots/
└── pyproject.toml
```
