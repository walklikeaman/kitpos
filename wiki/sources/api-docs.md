---
type: source
created: 2026-05-07
updated: 2026-05-07
source_paths: [Context/kit-api-reference.html, Context/swagger.json, "Context/swagger (1).json"]
---

# API Documentation Files in Context/

Three files. Two distinct APIs.

## 1. `kit-api-reference.html` — KIT POS / Maverick processor API

Single-page HTML reference (~33 KB stripped). Dark-themed sidebar layout, no external deps. Mirrors the API exposed by `dashboard.maverickpayments.com/api` (and `kitdashboard.com/api` for DBA endpoints).

**Sections (H2):** Authentication, Errors & Response Codes, Filters, Pagination, Payment Gateway, Boarding Applications, DBA (Merchant Accounts), Reporting, Customer Vault, ACH (Bank Transfers), Attachments, Tickets (Support), Residuals, Address Check, BIN Lookup, Recurring Payments, 3D Secure, Webhooks.

**Canonical reference:** the comprehensive endpoint table with auth headers, sandbox URL, UI-controller routes (logo upload, VAR PDF download), and the 403 / Cloudflare gotcha lives in user memory at `reference_kit_api_endpoints.md`. Sourced from `developers.kitdashboard.com/dashboard.md`. Updated 2026-05-05.

**Concept page:** [kit-api](../concepts/kit-api.md) — what's used by which workflow + current token / scope status from the WhatsApp chat.

## 2. `swagger.json` and `swagger (1).json` — Uber Public API (delivery + Eats)

**Both files are identical** (`diff -q` is empty). OpenAPI 3.0.1, title `Public API`, version `v1`, server `https://{{public-api-url}}` (template — staging). 75 paths across 30 tags.

This is **Uber's** API for delivery / Uber Eats integration, not KIT's. Relevant because Uber Eats is one of the delivery destinations under evaluation — see [delivery-vendors](../concepts/delivery-vendors.md). OAuth2 auth, JSON, with webhook support for orders / menus / storefront / delivery / store-pairing domains.

Tag groups: `auth`, `ping`, `delivery`, `direct_orders`, `orders` / `manager_orders`, `menus` / `manager_menu`, `storefront` / `manager_storefront`, `inventory`, `reports`, `reviews`, `finance`, `account_pairing`, `storelinks`, `organization`, `store`, `manager_loyalty`, `utils`, `callback`, plus matching `*_webhooks` for each domain.

**Concept page:** [uber-public-api](../concepts/uber-public-api.md).

## What's NOT here

- **PAX Marketplace REST API** — no docs in `Context/` yet. Quote pending from PAX (paid premium). Once obtained, expect API base under `https://api.paxstore.us/p-market-api`. See [file-build-flow](../concepts/file-build-flow.md).
- **Sunmi MAX / cloud APIs** — only the dev-portal URL `developer.sunmi.com` referenced in chat; no offline copy.
- **Docuseal / WeSign APIs** — only `docuseal.com/docs/api` URL referenced.
- **Instacart Connect** — `docs.instacart.com/connect/` referenced; PDF `Context/instacart_onboarding_requirements.pdf` covers what they need from us, not their API surface.
