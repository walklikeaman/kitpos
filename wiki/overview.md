---
type: overview
created: 2026-05-07
updated: 2026-05-07
sources: []
---

# KIT POS — Overview

Stub. Will be filled out as sources are ingested.

## What this repo is
Monorepo of automation agents for KIT POS merchant onboarding and PAX terminal provisioning. See [README.md](../README.md) for the canonical agent list and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for the technical layout.

## Agents (one-liners)
- **maverick-terminal-agent** — PAX Store provisioning (VAR fetch → merchant/terminal create → BroadPOS Push Template → TSYS params).
- **kit-dashboard-merchant-data** — KIT Dashboard API VAR lookup by MID/name; logo upload.
- **kit-dashboard-agent** — Merchant onboarding from documents (OCR/MICR + form fill).
- **amazon-purchase-agent** — Purchase automation (scope TBD on first ingest).

## Domain glossary (placeholder)
Will become real `concepts/*.md` pages on first mention: VAR sheet, MID, BroadPOS, Push Template, TSYS Sierra, ACH change request, KIT Dashboard.

## Stakeholders
TBD on first ingest.

## Current state
TBD — fill on first ingest of recent correspondence or status doc.
