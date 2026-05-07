---
type: source
created: 2026-05-07
updated: 2026-05-07
source_paths:
  - Context/MAVERICK_CHAT_CONTEXT.md
  - Context/NEW_CHAT_CONTEXT.md
  - Context/MONOREPO_STATUS.md
  - Context/README.md
  - Context/VIBEPROXY-CLAUDE-CODE-SETUP.md
  - Context/*.js
  - Context/KIT*N8N*.json
  - Context/applications.json
  - Context/merchants.json
---

# Context/ scaffolding artefacts

Historical / draft files used to bootstrap automation work, kept around for reference but not part of the live runtime. None of them is the source of truth for current behaviour — each entry below points to where the live truth lives.

## Hand-written context dumps (2026-04-24 snapshots)

- `MAVERICK_CHAT_CONTEXT.md` (589 lines) — original onboarding doc for Maverick Terminal Agent. Describes a 2-agent monorepo state.
- `NEW_CHAT_CONTEXT.md` (410 lines) — paired onboarding doc for Kit Dashboard Agent.
- `MONOREPO_STATUS.md` (187 lines) — status checklist after initial monorepo setup.
- `README.md` (150 lines) — early root README mirror.

**Status:** stale. Repo now has **4 agents** (`maverick-terminal-agent`, `kit-dashboard-merchant-data`, `kit-dashboard-agent`, `amazon-purchase-agent`), and the data models in code have evolved. Use these only for "why did it look that way originally?" archaeology.

**Live truth instead:**
- Current root: [README.md](../../README.md), [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md), [docs/SETUP.md](../../docs/SETUP.md), [docs/DEVELOPMENT.md](../../docs/DEVELOPMENT.md).
- Agent docs: each agent's own `README.md` and `AGENT_CONTEXT.md` (e.g. [AGENT_CONTEXT.md](../../agents/kit-dashboard-merchant-data/AGENT_CONTEXT.md)).
- Data models: `agents/*/src/*/models.py`.

## JS code snippets

Files like `Maverick.js`, `Maverick add merchant and add terminal.js`, `Get Merchant Data example *.js`, `Get VAR.js`, `Creating download file.js`, `kitdashboard.js`, `PAX Process.js`, `Add items from orders.js`, `Add new address in amazon.js`, `Choose address.js`, `Proceed with the order.js`, `Recuring order.js`.

These are reference / draft scripts that informed the design of the Python agents. They are not run directly. The corresponding production logic now lives in:

- `agents/maverick-terminal-agent/scripts/paxstore_provision_from_pdf.py` and `services/paxstore.py` (replaces `Maverick.js`, `PAX Process.js`, `Creating download file.js`, `Get VAR.js`).
- `agents/kit-dashboard-merchant-data/` (replaces `Get Merchant Data example *.js`, `kitdashboard.js`).
- `agents/amazon-purchase-agent/` (replaces `Add new address in amazon.js`, `Choose address.js`, `Proceed with the order.js`, `Recuring order.js`).

## N8N workflow exports

`KIT Merchant Lookup N8N.json` (+ `_fixed`), `KIT Onboarding N8N.json` (+ `_fixed`), `KIT POS Assistant N8N.json` (+ `_fixed`), `KIT POS Assistant.json`. Workflow definitions for the n8n instance.

**Live truth:** user memory `n8n_credentials.md` (API key, webhook URL, workflow IDs, credential IDs, infra notes).

## Data exports

`Context/applications.json`, `Context/merchants.json` and root-level `applications.json`, `applications.csv`, `merchants.json`, `merchants.csv`. Snapshots of KIT Dashboard data pulled via API. Not authoritative — re-pull when needed using endpoints in [kit-api](../concepts/kit-api.md).

## Off-topic

`VIBEPROXY-CLAUDE-CODE-SETUP.md` — Russian-language tutorial on using Claude Code via VibeProxy + Antigravity. Personal tooling note, unrelated to KIT POS. Not ingested.
