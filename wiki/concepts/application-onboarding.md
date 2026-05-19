---
type: concept
created: 2026-05-07
updated: 2026-05-10
sources: [whatsapp-gahl-oren, agent-context-merchant-data, session-2026-05-10-smoker-friendly]
---

# Merchant Application Onboarding (KIT Dashboard)

Workflow for boarding a new merchant on `kitdashboard.com`. Performed by Nikita; reviewed and finalised by Gahl.

## Inputs

- Merchant info pack from Gahl: usually a 5-page PDF (e.g. `2026-03-01_091518.pdf`) plus DL / Social Card. Sometimes incomplete — flag missing fields (EIN/SSN, DBA, EBT FNS license, voided check) instead of guessing.
- Voided check or bank letter (for direct deposit). The check must be voided, not just blank.
- Driver's License (DL) — front (and sometimes back) — uploaded to the docs section.

## Standard fields and their gotchas

- **Campaign**: type `KIT POS` first, then select **KIT POS Interchange Plus** (or **Traditional** = also Interchange-plus per Gahl, used for some accounts). Selecting before typing returns wrong campaigns.
- **Business type → principal title** (Gahl's hard rule):
  - Sole Proprietorship → **Owner**
  - Corporation / LLC → **CEO**
- **DBA vs legal name**: always confirm. Several times the legal entity ("Alhangry Inc.") was different from the DBA ("E 1 Four Mini").
- **EIN / Tax ID**: 9 digits. SSN may double as EIN for sole props.
- **Bank account**: never copy from a picture-OCR feature — type from the check by hand. Typos here cause sales settlements to disappear.
- **EBT**: if the source pack contains an EBT license, upload it AND enter the EBT FNS license number on the processing page (e.g. ALSHUJA MARKET).
- **MCC / business category**: smoke shop vs grocery distinction matters; ask Gahl when unclear.
- **Foundation date**: cannot be a future date — substitute the upcoming month's first if the merchant gave a future date.

## Drafting flow

1. Open the link Gahl sends, e.g. `https://kitdashboard.com/boarding/public/modify?id=<id>&guest=&token=<uuid>`. Existing apps come with a `guest=<base64-email>` param.
2. Fill all fields from the source pack. For unknowns, mark "NO" / leave blank and list the gaps when reporting back.
3. Submit as draft (do not finalise). Tell Gahl which fields are unverified — he confirms or corrects.

## Operator-side automation status

- Nikita created an application via the KIT Dashboard API on 2026-05-02 using a token issued by Gahl on 2026-05-01 (scope: boarding apps + tickets only — no merchant data scope yet).
- Token cannot delete applications — the underlying processor purges them periodically.
- Admin / merchant-data scope is gated on Ran (see [Ran](../entities/ran.md)).

## API-driven onboarding rules (verified 2026-05-10)

These rules apply when an agent (LLM, script, future Kit operator
playbook) creates or updates a boarding application via the
`dashboard.maverickpayments.com/api/boarding-application` endpoints.
Source of truth for the merchant-data Python implementation is
`agents/kit-dashboard-merchant-data/AGENT_CONTEXT.md`. This section
mirrors the API-level rules in one place so a TS agent can follow
them too.

### UPDATE existing > CREATE new

The KIT API token cannot delete applications — only the underlying
processor purges them periodically. So a pile of test/orphan
applications accumulates. Reuse them.

**Test-app pool (state as of 2026-05-19 — keep updated):**
| App ID | Status | Notes |
|---|---|---|
| 758354 | Free (sanitised 2026-05-10) | "Test Company LLC" placeholder; document attachment 29351960 unlinked from this app — was a real DL/check that confused operators |
| 756689 | Free (empty since creation) | minimal skeleton |
| 756683 | Free | "Test Company LLC" placeholder |
| 756692 | **In use — SMOKER FRIENDLY LIVERMORE** | started 2026-05-10 |
| 764333 | Free (empty) | created by agent, never used |
| 764195 | Free (empty) | created by agent, never used |
| 764192 | Free (empty) | created by agent, never used |
| 762713 | Free (sanitised 2026-05-19) | was "MT Electronics Inc" — invented name, real principal data; sanitised back to placeholder |
| 762710 | Free (sanitised 2026-05-19) | was "MT Electronics Inc" — invented name, real principal data; sanitised back to placeholder |

> ⚠️ When sanitising a test app, ALWAYS overwrite with the standard
> placeholder ("Test Company LLC", EIN 111111111, address 123 Test
> Street / Testville CA 90001, principal Test User CEO 111-11-1111,
> bank 000000000 / 0000000000) AND set
> `serviceDescription: "TEST APPLICATION — DO NOT PROCESS. Reusable
> test slot for the kitpos-operator agent."` so anyone glancing at
> the app can see at a glance that it's not real. Real-looking data
> in a test app actively harms — confused staff almost ran a real
> processor flow on Minna Mart before this rule was set.

> ⛔ NEVER invent any data field — company name, DBA, address,
> EIN, SSN, routing/account number, phone, email, or any other
> value. If it is not in the operator's documents or messages,
> leave it blank and ask. Invented names like "MT Electronics Inc"
> in test slots caused real confusion in the KIT Dashboard (2026-05-19
> incident). This rule applies equally to test slots and real
> onboardings.

When asked to onboard a new merchant: call kit_list_test_apps, take
the OLDEST free slot (is_recycled_test_slot=true, status='New'),
overwrite all fields. Only POST a brand-new application when the pool
has ZERO free slots. Applications cannot be deleted manually — only
the processor purges them periodically — so a free slot will almost
always exist.

### Documents to attach

ONLY two document categories are uploaded to the application:

| File type | Document type ID | Field on form |
|---|---|---|
| **Voided check** | 6 | "Voided Check" |
| **Driver's License / any govt ID** (passport, state ID, immigrant card) | 18 | "Driver's License" |

**Each document must be uploaded as a separate file.** If the merchant
sends a multi-page PDF (application + passport + check), extract each
relevant page as its own PDF before uploading. Never upload a combined
PDF that contains both documents at once — it attaches to both document
types incorrectly.

Other document categories — **never** attach to the application:
- IRS EIN letter (CP575B / CP575A)
- Seller's permit / sales-tax certificate
- Articles of Organization, Operating Agreement, Bylaws
- Lease, utility bill, business license
- DBA filing receipt

These are **data sources only** — the agent reads them, extracts
fields, and discards. Processor sees raw documents only via the
shared drive / boarding portal, not the API record.

API: `POST /attachment/upload` (multipart) → `POST /boarding-application/{id}/document` with
`{"attachment":{"id":N},"about":[6 or 18]}`. To remove: `DELETE
/boarding-application/{id}/document/{attachment_id}`.

### Principal — fields and rules

- **Name:** First + Last only. **Drop middle name** even if it
  appears in the EIN letter or DL. Source preference: DL `LAST NAME`
  + `FIRST NAME` fields. EIN letter only gives the responsible
  party's name, not always full legal.
- **Title:** Depends on entity type:
  - `LLC` or `Corporation` → **`"CEO"`**
  - `SoleProprietorship` (Individual) → **`"Owner"`**
  - Override to President / Manager / Partner only if a document
    explicitly states that title.
  Previous rule said "never use Owner" — corrected 2026-05-19: the
  API accepts Owner and it is the correct title for Sole Props.
- **Ownership:** 100% by default for single-member LLC and Sole Prop.
  **Multi-member LLC requires explicit ownership split** — see the
  detection rule below. Don't blindly set 100%.
- **Nationality:** US (`{"id": 199}`) — always. All principals live in
  the United States. Never set a foreign nationality.
- **Country — company address:** `{"id": 229}` (US).
- **Country — principal address:** `{"id": 199}` (US). Different lookup
  table from company address. Using 229 for a principal shows Afghanistan
  in the UI — always use 199 for principal addresses.
- **Personal guarantee + signer + management:** `"Yes"` for the
  primary principal.

### Multi-member LLC detection

The IRS EIN letter (CP575B) lists a "Form Due Date". If it shows
**Form 1065**, the entity is a multi-member LLC or partnership —
ownership is split among multiple members. Single-member LLCs file
1040 / Schedule C, NEVER 1065.

When 1065 is present and the agent only has one principal: ask the
operator for the rest before submitting. Don't fake 100%.

### Standard fields (KIT POS defaults)

| Field | Default | Override condition |
|---|---|---|
| `campaign.id` | 1579 (KIT POS Interchange Plus) | Gahl says Traditional → still 1579, label varies |
| `mcc.id` | 5912 generic (Drug Stores / Convenience) — *not a smoke-shop default; ALWAYS pick by business* | Smoke / cigar / tobacco → 791 (MCC 5993) |
| `processingMethod` | `"Acquiring"` | — |
| `equipmentUsed` | `"KIT POS"` | — |
| `businessLocation` | `Office Building / Rents / Commercial / 501-2500` | bigger merchant → adjust square footage |
| `processing.sales` | `swiped: 100, mail: 0, internet: 0` | E-commerce merchant — change |
| `intendedUsage.creditCards` | Yes | — |
| `intendedUsage.pinDebit` | Yes | — |
| `intendedUsage.amex.optBlue` | **Yes** *(AMEX OptBlue is on by default)* | — |
| `intendedUsage.ebt` | No | EBT license provided → Yes + upload license |
| `processing.volumes.monthlyTransactionAmount` | 50000 | merchant volume estimate |
| `processing.volumes.avgTransactionAmount` | 50 | — |
| `processing.volumes.maxTransactionAmount` | 500 | high-ticket merchant — raise |
| `bankruptcy.hasBankruptcy` | "Never" | document indicates otherwise → "Yes" |
| `seasonalBusiness.isSeasonal` | "No" | — |
| `inventory.onSite` | "Yes" | retail with store → Yes; pure delivery → No |
| `recurringPayments.hasRecurring` | "No" | — |
| `refundPolicy` | "No Refunds" | merchant has formal policy → fill verbatim |

**Tariffs (`processing.feeSchedule.fees[]`) — never touch.** Pricing
is set by the operator in the dashboard UI.

### Founded date — source priority

1. EIN issue date from IRS Letter CP575B (most authoritative)
2. Seller's Permit / business license start date
3. Operating Agreement formation date
4. **If no tax/government document with an issue date is present →
   use the 1st day of the current month** (e.g. 2026-05-01).
   Never use today's date; always the 1st of the month.
5. Never set a future date. If computed date is in the future,
   use the 1st of the current month instead.

`founded` field format: ISO `YYYY-MM-DD`.

### Entity type — detection workflow

Parse all uploaded documents first, then classify:

| Document phrasing | `company.type` (API value) | Principal title |
|---|---|---|
| "Inc", "Corp", "Corporation" | `Corporation` | `CEO` |
| "LLC" | `LLC` | `CEO` |
| "Partnership", "LP", "LLP" | `Partnership` | `CEO` |
| Sole proprietor / no entity suffix / owner name = company name | `Individual` | `Owner` |

> ⚠️ API uses `"Individual"` for Sole Proprietorship — NOT `"SoleProprietorship"`. Sending the wrong value returns HTTP 422.

**Sole Proprietor signals:**
- EIN letter shows an individual's name (not a business entity name)
- No "LLC", "Inc", "Corp" suffix anywhere in the documents
- Voided check holder name matches personal name on DL
- Application form lists individual name as both owner and business name

**For Sole Proprietors:**
- `company.name` = owner's full legal name (no separate business entity)
- `company.type` = `SoleProprietorship`
- `principal.title` = `Owner` (not CEO)
- EIN may be same as SSN — flag as warning but proceed
- No separate DBA needed unless merchant operates under a trade name

Don't guess from voided check footer alone — cross-check with EIN
letter or seller permit for the definitive entity type.

### Government ID — Passport, Immigrant Card, etc.

Any government-issued photo ID (Driver License, US Passport, Immigrant ID / Green Card, State ID) is uploaded as document type 18 ("Driver License") and its number + expiration date go into the `driverLicense` fields of the principal. The `state` field can be omitted (`{"id": null}`) for passports since they have no state.

### Blank check vs. Voided check

A blank (unfilled) check is accepted as a voided check if it clearly shows the MICR line with routing and account numbers. No "VOID" stamp required.

### Sole Proprietor — EIN equals SSN

For `Individual` (Sole Proprietor) entities, use the owner's SSN as the `federalTaxId`. The form field "Federal Tax ID" may say "sole proprietorship" instead of a number — in that case use the SSN from Owner's Information.

### API payload structure (verified)

The correct PUT body nests fields differently from what the UI suggests:

```json
{
  "dba": {"sameAsCompany": "No", "name": "...", "address": {...}},
  "businessLocation": {"buildingType": "...", "buildingOwnership": "...", "areaZoned": "...", "squareFootage": "..."},
  "customerServiceContact": {"phone": "...", "email": "..."},
  "corporateContact": {"phone": "...", "email": "..."},
  "processing": {
    "banks": [{"type": "All", "routingNumber": "...", "accountNumber": "..."}],
    "intendedUsage": {...},
    "volumes": {...},
    "sales": {...}
  }
}
```

Key differences from naive structure:
- `"dba"` (object, not `"dbas"` array)
- `"processing.banks"` (not top-level `"bankAccounts"`)
- `"processing.intendedUsage"` (not top-level `"intendedUsage"`)
- `"businessLocation"` at top level (not inside `"dba"`)

### KIT API ergonomics (verified the hard way)

- **`null` is ignored.** PUT'ing `"phone": null` does NOT clear an
  existing value. Use `"phone": ""` (empty string).
- **Nested object fields can't always be cleared.** PUT
  `"driverLicense": {"state": null}` may leave `state.id` set from
  a prior value. Workaround: PUT the entire object with explicit empty
  strings (`{"number":"", "expiration":"", "state": null}`); accept
  some metadata residue.
- **ZIP must be exactly 5 digits.** ZIP+4 like `94551-9212` returns
  HTTP 422 `"company.address.zip must be 5 digits"`. Strip the `-9212`.
- **State, country, nationality use internal numeric IDs**, not
  postal codes. California = 5, US country = 229, US nationality =
  199. See `_STATE_CODES` in `agents/kit-dashboard-merchant-data/.../models.py`
  for the full 50-state map (DC = id 9; FL = 10; … OK = 37; TX = 44).
- **MID lookup via `filter[company.mid]` is broken (returns 422).**
  Page-scan `/merchant?per-page=50&page=N` and match
  `dbas[*].processing.mid` locally. ~13 pages for 627 merchants.
- **Document type IDs:** 6 = Voided Check, 18 = Driver License,
  3 = Other (do **not** use Other for DL or Check — pick the proper id).

### Validate semantics

`GET /boarding-application/{id}/validate` returns:
- `[]` (empty list) → no errors, ready for `PUT
  /boarding-application/{id}/status/Underwriting`
- Empty fields will populate the error dict with messages like
  `"principals[1051544].ssn": "Social Security Number cannot be blank."`

If the application has stale test data (`+1 213-555-0100`,
`test@example.com`), validate may pass falsely. Always clear those
explicitly to `""` before validating, then re-run validate to see
the real gap list.

### Run logging

Every onboarding run (success or fail) appends to
`agents/kit-dashboard-merchant-data/runs/runs.jsonl`. From a TS / API
caller, mirror this by POSTing to a Supabase log table or local file.
Required minimum:

- `merchant_name`
- `app_id` (even on partial fails)
- `source_documents` — paths or sha256 of the inputs
- `principal_name` (post-extraction)
- `entity_type`
- `documents_attached` — list of `{type, attachment_id}`
- `notes` — anything non-standard

### Submit for underwriting

`PUT /boarding-application/{id}/status/Underwriting` — never call
this automatically. Always stop one step before, return the merchant
review URL, let a human confirm. Hard rule.

## Cross-references

- Source: [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
- API rules ported from: `agents/kit-dashboard-merchant-data/AGENT_CONTEXT.md` § "Онбординг мерчантов: обязательные правила"
- Follow-up workflows: [file-build-flow](file-build-flow.md), [dda-update-flow](dda-update-flow.md).
- Related agents:
  - `agents/kit-dashboard-agent/` — Python onboarding (CLI, OCR/MICR parsing)
  - `agents/kit-dashboard-merchant-data/` — Python merchant lookup + boarding API client (`MerchantOnboardingService`)
  - `kitpos-operator/` — TypeScript Kit operator agent that will host the chat-driven `onboard_merchant` playbook (sister repo: github.com/walklikeaman/kitpos-operator)
