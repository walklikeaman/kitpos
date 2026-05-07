---
type: concept
created: 2026-05-07
updated: 2026-05-07
sources: [api-docs, whatsapp-gahl-oren]
---

# Uber Public API (Delivery + Eats)

OpenAPI 3.0.1 spec, 75 paths across 30 tags. Auth via OAuth2. JSON over HTTP plus webhooks per domain. Server template `https://{{public-api-url}}` (the spec is staging-flavored — production base must come from Uber).

This is **Uber's** API, used for the Uber Eats / Uber Direct delivery integration we may build for KIT POS merchants. Per Gahl (chat, 2026-04-21): "Uber Eats is most accessible for us." See [delivery-vendors](delivery-vendors.md) for the broader vendor landscape.

## Domains we'd actually use

| Tag | What it covers | Why we'd use it |
|---|---|---|
| `auth_endpoints` | OAuth2 token mgmt | Required to call anything |
| `manager_menu_endpoints` + `menus_endpoints` | Menu publish, sync, entity availability suspend/unsuspend, hours | Push our product DB → Uber Eats menu, mark items in/out of stock |
| `manager_storefront_endpoints` + `storefront_endpoints` | Pause/unpause store, hours, eater-side status | Auto-pause when register goes offline / closes |
| `manager_order_endpoints` + `orders_endpoints` | Order create/cancel/confirm/fulfill, items, prep-time, ready-to-pickup, packaging-component | Push incoming Uber orders into POS, ack lifecycle back |
| `delivery_endpoints` | Quote / accept / cancel / status / update | For Direct (we book courier) flows |
| `inventory_endpoints` | Shipments, summaries | Stock reconciliation |
| `direct_orders_endpoints` | Get orders directly | Polling fallback if webhooks fail |
| `reports_endpoints` + `reviews_endpoints` | Generate report jobs, reply to reviews | Operational |
| `organization_endpoints` | Org / brands / stores hierarchy + connections | Map our merchant model → Uber's brand→store tree |
| `store_endpoints` + `account_pairing_endpoints` + `storelinks_endpoints` | Onboarding/offboarding, status | Connect a new merchant the first time |
| `finance_endpoints` | Financial invoices/transactions | Settlement reconciliation |
| `manager_loyalty_endpoints` | Rewards: evaluate / redeem / accumulate / refund / simulate, user enrollment | If we want to pass our loyalty into Uber |

## Webhook domains (mirrors of the above)

`orders_webhooks`, `manager_orders_webhooks`, `menus_webhooks`, `storefront_webhooks`, `delivery_webhooks`, `account_pairing_webhooks`, `storelinks_webhooks`, `reports_webhooks`, `ping_webhooks`. All event-type-driven.

## Architectural implication

To make this useful for KIT POS we need:

1. **Webhook receiver** — single ingress to handle order/menu/storefront events, fan out to per-merchant POS instances.
2. **Stock model coupling** — Ran's preference (daily inventory sync) is at odds with Uber's model where item availability is real-time. Discussed in [delivery-vendors](delivery-vendors.md).
3. **Quantity / Size column** in our product DB for alcohol and cigarettes.
4. **Brand / store hierarchy mapping** — KIT's merchant-account → DBA → terminal model needs to map to Uber's organization → brand → store.

## Cross-references

- Source: [api-docs](../sources/api-docs.md), [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
- Related: [delivery-vendors](delivery-vendors.md) — competitor / alternative integration paths.
