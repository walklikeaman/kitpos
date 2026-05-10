# Wiki Index

Catalog of every page in this wiki. Read this first when answering project questions.

## Overview
- [overview.md](overview.md) — KIT POS project at a glance

## Entities
- [Gahl Oren](entities/gahl-oren.md) — partner / operator at KIT POS, primary point of contact
- [Ran](entities/ran.md) — Gahl's brother, engineering lead; gatekeeper for admin scopes
- [Bakil](entities/bakil.md) — sales agent, sources merchant accounts
- [KIT POS, Inc.](entities/kit-pos-org.md) — the company: platforms, hardware lineup, banking ops

## Concepts
- [Application Onboarding](concepts/application-onboarding.md) — KIT Dashboard boarding workflow + field gotchas
- [File Build Flow](concepts/file-build-flow.md) — PAX Store + BroadPOS TSYS Sierra provisioning, VAR-sheet field mapping
- [PAX Store Provisioning Scenarios](concepts/paxstore-provisioning-scenarios.md) — regular (POS-paired) vs stand-alone build patterns + intent classification
- [DDA Update Flow](concepts/dda-update-flow.md) — bank-account-change ticket + Docuseal/WeSign signing
- [Pricing Change Flow](concepts/pricing-change-flow.md) — two-ticket workflow for discount-schedule changes
- [Sunmi Provisioning](concepts/sunmi-provisioning.md) — Atlassian ticket → MDM remark → Transfer Device
- [Kit Operator Agent](concepts/kit-operator-agent.md) — TS chat agent on Render that fronts onboarding via Telegram + Claude Code; 12 tools, vision parser, crops, full playbook
- [KIT Apps × Device Matrix](concepts/kit-apps-by-device.md) — what to push to A35 / A3700 / L1400 / Sunmi / A800
- [Delivery Vendors](concepts/delivery-vendors.md) — Otter / Deliverect / Instacart / NRS landscape
- [KIT POS / Maverick API](concepts/kit-api.md) — base URLs, auth, current token scope; pointer to full memory reference
- [Uber Public API](concepts/uber-public-api.md) — Uber Eats / Direct OpenAPI surface; relevant to delivery integration

## Sources
- [WhatsApp — Gahl Oren](sources/whatsapp-gahl-oren.md) — chat 2026-01-16 to 2026-05-05, ~4 months of project context
- [API docs](sources/api-docs.md) — KIT API HTML reference + Uber swagger.json; what's in `Context/`
- [Context/ scaffolding](sources/context-scaffolding.md) — stale 2026-04-24 onboarding dumps + draft JS / N8N exports / data snapshots

---

Format for each entry: `- [title](path) — one-line hook`. Keep entries under ~150 chars. Organize by category, not date.
