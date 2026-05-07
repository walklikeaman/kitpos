---
type: concept
created: 2026-05-07
updated: 2026-05-07
sources: [whatsapp-gahl-oren, session-2026-05-07-q25-a80]
---

# KIT Apps × Device Matrix

Which apps to push to which device when building a download file. The non-obvious rule is **KIT Back Screen on A3700 only, never on A35**.

| Device | Role | Firmware push | Apps to push |
|---|---|---|---|
| Sunmi POS (default) | Cash-register tablet | (handled via Sunmi MDM) | KIT POS, KIT Merchant, KIT Stock |
| **PAX A35** | Modern PIN Pad (default modern set) | latest | **BroadPOS TSYS Sierra only** (no KIT Back Screen) |
| **PAX A3700** (Elys) | PIN Pad of the Elys set | latest | **KIT Back Screen + BroadPOS TSYS Sierra** |
| **PAX L1400** (Elys) | POS of the Elys set | latest | KIT POS, KIT Merchant, KIT Stock |
| **PAX A800** | Standalone PIN Pad (no POS) | latest | BroadPOS TSYS Sierra; ALSO fill the Receipt tab |
| **PAX Q25** | "Dumb" PIN Pad cabled to a Smart POS (e.g. A80). Does not run Android apps. | **none** | **none** — register in PAX Store and stop. PIN entry / card read only |
| **PAX A80** | Smart POS host for a Q25 (stand-alone configuration) | latest | BroadPOS TSYS Sierra via template `KIT-Android`; ALSO fill Receipt tab + switch POS mode to **Internal POS** |

## App overview

- **KIT POS** (default v202 auto-installs on Sunmi/L1400) — the cashier app.
- **KIT Merchant** — owner / admin app: clerks, permissions, reports, menu items, specials.
- **KIT Stock** — inventory management: descriptions, costs, prices, inventory levels, shelf labels.
- **KIT Back Screen** — customer-facing display app for the second screen of the Elys A3700 PIN Pad.
- **BroadPOS TSYS Sierra** — TSYS payment app on PIN Pads. Configured per-merchant from the VAR sheet (see [file-build-flow](file-build-flow.md)).

End users download KIT Merchant / KIT Stock from `download.kit-pos.com`.

## NRS exception

For merchants using NRS POS hardware, KIT POS apps are **not** installed. The PIN Pad still integrates via BroadPOS TSYS Sierra but with a different parameter template — to be created the next time an NRS deal comes in (Snack Zone, deferred 2026-05-04).

## Cross-references

- Source: [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
- Related: [file-build-flow](file-build-flow.md), [sunmi-provisioning](sunmi-provisioning.md).
