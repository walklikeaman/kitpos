---
type: source
created: 2026-05-07
updated: 2026-05-07
source_path: Context/WhatsApp Chat - Gahl Oren/_chat.txt
source_kind: whatsapp_export
date_range: 2026-01-16..2026-05-05
participants: [Gahl Oren, Nikita Oz Nakonechnyi]
---

# WhatsApp — Gahl Oren

Personal+work chat between Nikita (this user) and Gahl Oren over ~4 months. The work portion covers KIT POS onboarding, hardware ops, terminal provisioning, website build, and integration research.

Raw export: `Context/WhatsApp Chat - Gahl Oren/_chat.txt` (2494 lines) plus 143 photos / 92 audio / 19 PDFs / 1 mp4 in the same folder. Audio is omitted from this digest (no transcripts).

## Timeline (work)

- **Jan 16 – 22** — pre-collaboration; first technical exchange about a "Cheers" merchant: pending TSYS transactions traced to PIN Pad/POS IP-range mismatch and TSYS App not running.
- **Jan 27 – Feb 6** — tutorial videos work (Tutorials 1–6). Naming convention firmed up: "Updating Products and Inventory in KIT Stock — Part N". End line standardized to "Thank you for watching".
- **Jan 29 – Feb 2** — Nikita gets Maverick Assistant access (`nakonechnyi.n@gmail.com`), then dedicated `nikita@kit-pos.com`. First applications drafted via kitdashboard `/boarding/public/modify` flow.
- **Feb – Mar** — application onboarding cadence. Recurring corrections from Gahl: campaign must be "KIT POS Interchange Plus", entity-type → principal mapping (Sole Prop = Owner, Corp/LLC = CEO), DBA vs legal name, voided check requirement.
- **Mar 11** — first DDA / Bank Account Change Request workflow (Smokey Joe's 2.0). 1099-K Report retrieved from Reporting → Other.
- **Mar 15 – 19** — Amazon Business onboarding for hardware (Royal Mist first). Card splits: one for Volcora, one for Amazon. Repeated friction with Amazon address restrictions and approval workflows.
- **Mar 21 – 22** — first PAX Store + BroadPOS download-file build (Bay City, ELYS POS = A3700 + L1400). Template "KIT-Android" saved.
- **Mar 31** — Cal Mini Mart pricing change: two-ticket workflow learned (General ticket Daily-Discount move, then Pricing-Update ticket with downloaded form + cloned signature, Notify Merchant OFF).
- **Apr 3 – ongoing** — Nikita starts building [kit-pos.com](https://kit-pos-website.vercel.app) on Next.js / Vercel. Replaces the planned external designer.
- **Apr 19 – 24** — Sunmi flow learned end-to-end: provisioning ticket on `sunmi-1.atlassian.net` (Entity ID `ZE2FVADC6IG5Y`) → MDM remark = agent name → Transfer Device.
- **Apr 22 – May 5** — automation push: Nikita writes the Maverick browser agent (creates merchant / terminal / TSYS tab) → starts pushing for PAX Marketplace REST API access (PAX confirmed it's a paid premium feature, awaiting quote) and KIT Dashboard developer token (got partial token for boarding+tickets May 1; still needs admin/merchant scope).
- **Apr 26 – May 5** — vendor research for delivery integration: Otter (final terms $89/mo, $10K commit, 50 stores in 6 mo), Deliverect (now has retail), Checkmate, Nash (not a fit), Instacart (direct, requires onboarding), Saucey (no new direct), DoorDash (closed to new applicants), Uber Eats. ESL research started: Minewtag (American, expensive but full SDK), Zhsunyco (cheaper).

## Cross-references

- People: [Gahl Oren](../entities/gahl-oren.md), [Ran](../entities/ran.md), [Bakil](../entities/bakil.md), [KIT POS org](../entities/kit-pos-org.md).
- Workflows referenced: [application-onboarding](../concepts/application-onboarding.md), [file-build-flow](../concepts/file-build-flow.md), [dda-update-flow](../concepts/dda-update-flow.md), [pricing-change-flow](../concepts/pricing-change-flow.md), [sunmi-provisioning](../concepts/sunmi-provisioning.md), [kit-apps-by-device](../concepts/kit-apps-by-device.md), [delivery-vendors](../concepts/delivery-vendors.md).

## Notable artefacts referenced in chat (pointers to `Context/`)

- Application PDFs: `2026-03-01_091518.pdf`, `2026-03-31_085744.pdf`, `Cal Mini Mart.pdf`, `Castro Market Inc.pdf`, `El Camino Mart Inc.pdf`, `Delauers Reatil.pdf`, `Alum Rock Shop.pdf`, `Eldon Tobacco.pdf`, etc.
- VAR sheets: `*-KIT-POSVAR-Sheet*.pdf` (one per merchant).
- Bank Account Change Request: `BANK ACCOUNT CHANGE REQUEST*.pdf` + `Audit Log - MID CITY BANK ACCOUNT CHANGE REQUEST.pdf`.
- 1099-K: `1099K Report - 20260311-1146.pdf`.
- Hardware research deliverable: `ESL_Vendor_Highlights_KIT_POS_1.pdf`.
- Maverick automation scaffolding: `Maverick.js`, `Maverick add merchant and add terminal.js`, `Get Merchant Data example *.js`, `Get VAR.js`, `Creating download file.js`.
- N8N workflows authored later: `KIT Merchant Lookup N8N*.json`, `KIT Onboarding N8N*.json`, `KIT POS Assistant N8N*.json`.

## Open items as of 2026-05-05

- PAX Marketplace REST API — waiting on quote from PAX support.
- KIT Dashboard admin-scope token (merchant data) — Ran will provision, blocked.
- Amazon SP-API onboarding — registration verified, developer profile next; Ran wants to do final registration himself.
- Sunmi ESL contact — Sunmi sent a vendor lead, no response yet; Nikita researching alternatives (Minewtag, Zhsunyco, Silabs).
- Otter commitment — under reconsideration with Ran.
- Sunmi V3 Plus — Gahl purchasing in the US.
- Statesboro Vape Shop — order pending tablet selection (12.4" AT&T refurbished agreed).
- Pady C Store — file build done, NRS template for Snack Zone deferred to next session.
- Website (`kit-pos-website.vercel.app`) — Hardware section being polished (P3H = Payment Terminal, CPad = Tablet POS, MP7001 = Scanner Scale; payment-terminal screen image still being iterated).
