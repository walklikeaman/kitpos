# KITPOS Agents

Monorepo for KIT POS automation agents.

## Agents

### [Maverick Terminal Agent](./agents/maverick-terminal-agent)
PAX Store provisioning agent. Fetches VAR data from KIT API, creates merchants and terminals, pushes firmware, installs BroadPOS TSYS Sierra via Push Template, and fills TSYS parameters — headless by default.

- Strict provisioning rules: [`docs/PAXSTORE_PROVISIONING_RULES.md`](./agents/maverick-terminal-agent/docs/PAXSTORE_PROVISIONING_RULES.md)
- Run history: `tmp/run-history/paxstore_runs.jsonl`
- CLI: `python3 scripts/paxstore_provision_from_pdf.py`

### [KIT Dashboard Merchant Data](./agents/kit-dashboard-merchant-data)
Merchant VAR data lookup agent. Fetches TSYS VAR sheets from KIT Dashboard API by MID or merchant name. Supports logo upload/removal.

- Full context: [`AGENT_CONTEXT.md`](./agents/kit-dashboard-merchant-data/AGENT_CONTEXT.md)
- CLI: `merchant api-var-by-mid <MID>` | `merchant upload-logo logo.png --mid <MID>`

### [KIT Dashboard Agent](./agents/kit-dashboard-agent)
Merchant onboarding automation. Processes merchant documents (checks, IDs) via OCR/MICR and fills KIT Dashboard forms.

- CLI: `kit parse-docs` | `kit plan` | `kit execute`

## Structure

```
kitpos/
├── agents/
│   ├── maverick-terminal-agent/      # PAX Store provisioning
│   ├── kit-dashboard-merchant-data/  # VAR data lookup + logo upload
│   └── kit-dashboard-agent/          # Merchant onboarding docs
├── docs/
└── scripts/
```

## Quick Start

```bash
# Maverick Terminal Agent
cd agents/maverick-terminal-agent
pip install -e '.[browser]'
python -m playwright install chromium

# KIT Dashboard Merchant Data
cd agents/kit-dashboard-merchant-data
pip install -e .
```
