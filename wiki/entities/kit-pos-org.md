---
type: entity
entity_kind: organization
created: 2026-05-07
updated: 2026-05-07
sources: [whatsapp-gahl-oren]
---

# KIT POS, Inc.

Boutique POS / payment-processing reseller. Resells Maverick payments processing on top of custom KIT-branded hardware and software. Customer base concentrated in smoke shops, liquor stores, grocery / convenience stores, and quick-service restaurants in the US.

## Public contact

- Website: `kit-pos.com` (legacy; new site under `kit-pos-website.vercel.app`, Next.js / React 19 / TS / Tailwind, deployed via Vercel — built by Nikita starting 2026-04-03).
- Email: `info@kit-pos.com`
- Phone: `(833) 314-5650`
- App downloads: `download.kit-pos.com` (KIT POS, KIT Merchant, KIT Stock).

## Stack of platforms used to operate

| Platform | URL | Purpose |
|---|---|---|
| KIT Dashboard | `kitdashboard.com` | Boarding, applications, merchant profile/branding, tickets, reports (incl. 1099-K under Reporting → Other) |
| Maverick portal | `dashboard.maverickpayments.com` | Underlying processor — Nikita has Assistant role |
| PAX Store / BroadPOS | `paxus.paxstore.us` | Terminal management, file builds, BroadPOS TSYS Sierra app |
| PAX Developer Center | `developer.paxstore.us` | Marketplace REST API keys (premium feature, quote pending) |
| Sunmi MDM | `partner.us.sunmi.com/mdm` | Device management; Entity ID `ZE2FVADC6IG5Y` |
| Sunmi service desk | `sunmi-1.atlassian.net/servicedesk/customer/portal/50` | Provisioning tickets |
| Amazon Business | `amazon.com` | Hardware procurement, KIT POS group |
| Volcora | `volcora.com` | Alternative printer source |
| Docuseal | `docuseal.com` (account `gahl@kit-pos.com`) | E-signature (DDA forms etc.) |
| WeSign | `wesign.com` | Earlier e-signature flow (template-based) |

## Hardware lineup (as displayed on the new website, 2026-05)

POS: Sunmi tablet POS variants. Payment terminal: **Sunmi P3H** (was PAX A35 historically). Tablet POS: **Sunmi CPad**. Mobile retail / label: **Sunmi V3 Plus**. 80mm receipt+label printer (Sunmi cloud-printing capable). Scanner scale: **Zebra MP7001**. Plus standalone scanners, cash drawers, kitchen printer.

Older alternative set seen in field: **ELYS POS** (= PAX A3700 PIN Pad + L1400 POS) — used when the merchant declined the Sunmi+A35 default.

## Banking ops

- Cards held by Gahl, separated by purpose:
  - One card for **Volcora only**.
  - One card for **Amazon only**.
  - "Cloude Card" for AI subscriptions (Claude $100 plan).
- Amazon Business has multiple cards on file; old Amex was expired as of mid-Apr 2026.

## Sources

- [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
