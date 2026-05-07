---
type: concept
created: 2026-05-07
updated: 2026-05-07
sources: [whatsapp-gahl-oren]
---

# Pricing / Discount-Schedule Change

Workflow for moving a merchant from one pricing schedule to another (e.g. Monthly Discount → Daily Discount, or rate updates). Learned end-to-end on Cal Mini Mart (B Only One Inc) on 2026-03-31.

This is a **two-ticket** workflow — opening a Pricing-Update ticket directly does not work.

## Ticket 1 — General ticket to switch discount cadence

- Category: **Other** → **General** (NOT a Pricing change category).
- Subject: `<Merchant DBA> Daily Discount` (e.g. `Cal Mini Mart Daily Discount`).
- Additional info: e.g. `Please change to Daily Discount.`
- Submit.

## Ticket 2 — Pricing Update

Only after submitting ticket 1, open a new **Pricing Update** ticket on the same merchant.

- Set the new pricing per the screenshot Gahl provides. For Interchange-Plus migrations the **qualified rate must be 0%** (different pricing program — leaving the legacy qualified rate triggers wrong settlements).
- Adjust monthly fee (e.g. $30) and monthly minimum (e.g. $25) to the agreed values.
- **Download the form** the ticket generates.
- **Switch OFF "Notify Merchant"** before submitting.

## Signing the form

The merchant doesn't sign here in real time — Nikita applies a copied signature pulled from the merchant's earlier signed application:

1. Open the merchant's application page.
2. Locate and copy the signature from there.
3. Paste under `<Legal entity name>`. Title: `President`. Add date.
4. Re-upload to the ticket. Body content can be `attached`. Submit.

## Cross-references

- Source: [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
- Related artefact: `Context/Form.pdf`, `Context/Form (1).pdf`.
