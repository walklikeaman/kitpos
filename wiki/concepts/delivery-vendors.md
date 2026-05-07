---
type: concept
created: 2026-05-07
updated: 2026-05-07
sources: [whatsapp-gahl-oren]
---

# Delivery / Marketplace Vendor Landscape

Research and decisions around integrating food / retail delivery into KIT POS, Mar–May 2026. Driven by Gahl; Nikita produced the comparative deliverable `Context/Delivery_Aggregator_Integration_KIT_POS.pdf`.

## Categories

- **Aggregators** — one tablet/integration that fans out to DoorDash, Uber Eats, Grubhub, etc. Cheaper per integration; revenue-share / commitment-based.
- **Direct integrations** — one-by-one with each marketplace. Higher engineering cost but more control.

## Vendors evaluated

| Vendor | Type | Status as of 2026-05-05 |
|---|---|---|
| **Otter** | Aggregator + order-management tablet | Final terms negotiated: $89/month + commitment of $10K and 50 stores in 6 months. Under reconsideration with Ran. Has retail. |
| **Deliverect** | Aggregator | Used to be restaurant-only; relaunched retail recently. Slow to respond. Awaiting reply. |
| **Checkmate** | Aggregator | Looks good per Gahl; not yet contacted. |
| **Nash** | Aggregator | 30-min call on 2026-04-27, not a fit (different service model). |
| **Saucey Direct** | Direct (alcohol) | No new direct integrations being accepted. |
| **Instacart Connect** | Direct | Onboarding-required. Will provide auth + API keys after Instacart-side approval. Gahl signed up via `gahl@kit-pos.com`. |
| **DoorDash** | Direct | Closed to new applicants. |
| **Uber Eats** | Direct | Most accessible per Gahl. |
| **Grubhub** | Direct | Wants to see KIT POS website before discussing — site finish is a precondition. |
| **NRS** | POS competitor with own DoorDash app | Has a tablet-app order management product (`nrsplus.com/doordash`). |

## Architectural notes (from chat)

- Inventory sync: Ran prefers **daily** stock updates, not per-sale live updates. Nikita argues stock should be near-real-time so out-of-stock items don't accept delivery orders. Open question.
- Approach proposed by Nikita: a separate stock DB / availability table that talks to the aggregator via its protocol, not direct mutation of merchant Stock DB on every sale.
- Sunmi 80mm cloud printer was considered as a delivery-order printout device — concluded it doesn't help unless POS still owns price/stock state.
- Adding a Quantity / Size column to the product DB is required for alcohol and cigarette listings on Instacart.

## Cross-references

- Source: [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
- Deliverable: `Context/Delivery_Aggregator_Integration_KIT_POS.pdf`.
