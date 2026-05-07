---
type: concept
created: 2026-05-07
updated: 2026-05-07
sources: [api-docs, whatsapp-gahl-oren]
---

# KIT POS / Maverick API

The HTTP API that powers KIT Dashboard. Used (or planned) for: agent-side automation of merchant onboarding, VAR sheet retrieval, ticket creation, attachment upload, branding/logo, reporting (incl. 1099-K pulls).

**The complete endpoint reference is in user memory** at `reference_kit_api_endpoints.md` (sourced from `developers.kitdashboard.com/dashboard.md`, 2026-05-05). Don't duplicate it here — read memory for the canonical table. This page covers the bits you need to use that table effectively in this project.

## Two base URLs (don't mix up)

| Base | Used for |
|---|---|
| `https://dashboard.maverickpayments.com/api` | Boarding applications, merchant, terminal, attachments, reporting, ACH, tickets |
| `https://kitdashboard.com/api` | **DBA** endpoints (the docs explicitly use this host) |
| `https://kitdashboard.com/merchant/profile/...` | UI-controller routes (logo upload/remove, VAR PDF download) — **session cookie auth, NOT Bearer token** |

Sandbox: `https://sandbox.kitdashboard.com/api` (separate API key).

## Auth & headers

- `Authorization: Bearer <KIT_API_KEY>`
- Required headers (Cloudflare WAF blocks Python's default UA): `Referer: https://kitdashboard.com/`, `Origin: https://kitdashboard.com`, browser-style `User-Agent`.

## Token status as of 2026-05-07

- Issued by Gahl on 2026-05-01 (chat 00:13): scope = boarding apps + tickets only.
  - Verified working: created an application via API on 2026-05-02 (chat 02:33).
  - Cannot DELETE applications (returns 403; the processor purges them periodically anyway).
- **Missing scope:** merchant data (phone/name lookup for hardware shipments), admin operations.
  - Blocked on Ran — see [Ran](../entities/ran.md). Ran is the gatekeeper.
- The agent `agents/kit-dashboard-merchant-data` works around this by hitting the UI-controller endpoints with a session cookie.

## Endpoint groups by workflow

| Workflow | Endpoints (see memory for full signatures) |
|---|---|
| [application-onboarding](application-onboarding.md) | `POST /boarding-application/create`, `PUT /boarding-application/<id>`, `GET /boarding-application/<id>/validate`, `PUT .../status/Underwriting`, `PUT .../request-signature` |
| [file-build-flow](file-build-flow.md) (data side) | `GET /api/dba`, terminal endpoints under DBA, `GET /merchant/profile/view-var-sheet?id=<merchantAccountId>&terminalId=<tid>` for the VAR PDF (UI-controller, cookie auth) |
| Logo / Branding | `POST /merchant/profile/upload-dba-logo?id=<dbaId>` multipart (UI-controller); `GET /merchant/profile/remove-dba-logo` |
| [dda-update-flow](dda-update-flow.md) | `POST /api/ticket`, `GET /api/ticket/categories`, `POST /api/attachment` |
| Reporting | `GET /api/reporting/{authorizations,batches,batches/summary,payouts,chargebacks,reserve,fraud-report}`, `POST /api/reporting/report` |

## Cross-references

- Source files: [api-docs](../sources/api-docs.md), [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
- Memory: `reference_kit_api_endpoints.md` (the source of truth — read it before recommending any specific endpoint)
- Repo agents that use this API: `agents/kit-dashboard-agent`, `agents/kit-dashboard-merchant-data`
