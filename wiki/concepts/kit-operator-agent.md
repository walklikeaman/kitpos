---
type: concept
created: 2026-05-10
updated: 2026-05-10
sources: [session-2026-05-10-path-c-build]
---

# Kit Operator Agent (kitpos-operator)

The TypeScript agent that operators (and colleagues) talk to over
Telegram instead of going through N8N. Hosted on Render free tier
at https://kitpos-operator.onrender.com, sister repo
[walklikeaman/kitpos-operator](https://github.com/walklikeaman/kitpos-operator).

Built to consume the same KIT Dashboard / Supabase / OpenRouter
infrastructure as the existing Python mini-agents, but expose a
chat-driven interface where the operator drops documents in
Telegram and the agent figures out what to do.

## Where it sits

```
        Telegram (anyone, no laptop required)
                │
                ▼
       @kit_operator_bot ────► Render Web Service
                                  │  (Hono + grammy webhook)
                                  ▼
                       Kit agent loop
                       (OpenRouter, openai/gpt-oss-120b:free)
                                  │
                                  ▼ tool calls
        ┌──────────────────────────────────────────────┐
        │                                              │
   Supabase Storage              KIT Dashboard API     │
   (kit-onboarding-uploads,      (boarding-application │
   crops, parses cache,          + merchant + MCC)     │
   pg_cron 7-day purge)                                │
                                                       │
   Vision LLM (Gemma-4 26B free + 4 fallbacks) ───────┘
```

## Channels

- **Telegram** — `@kit_operator_bot`. Webhook, secret-token
  validated. Photo/document uploads stream to Supabase Storage.
  Status messages edit in place (`🟡 → 🧠 → 🔧 → ✍️`),
  localised RU/EN by detection from user message text.
- **Programmatic / Claude Code** — `POST /v1/run` with a Bearer
  token (env `KIT_OPERATOR_API_KEY`). Same agent loop, same
  tools, returns `{thread_id, reply, tool_calls, ms, events}`.

## Tools (12, in three groups)

### Lookup (read-only)
| Tool | Effect |
|---|---|
| `kit_lookup_merchant({query})` | Search KIT Dashboard merchants by name fragment OR exact 12-digit MID. MID search uses page-scan because `filter[company.mid]` returns 422. Returns `{id, mid, name, status, city, state}`. |
| `kit_get_merchant_details({merchant_id})` | Full record by INTERNAL kit-dashboard id (NOT MID): DBA, MID, phone, email, full address, principal name. State id 37 → "OK" via internal map. |
| `kit_get_var_list({terminal_id?, merchant_id?})` | Pull a VAR sheet (TSYS terminal config). Source of truth for BIN, agent/chain, MID/store/TID, MCC. Only call when the operator explicitly asks for VAR. |

### Documents (upload + parse + crop)
| Tool | Effect |
|---|---|
| `kit_list_session_uploads()` | List every file uploaded to the current thread (Supabase Storage `kit-onboarding-uploads`, `tg-<chat>/` prefix). Zero args — runtime injects threadId. |
| `kit_parse_document({path, hint?, force?})` | OCR + structured extraction. Downloads file, renders PDFs to PNG (1.0× scale, max 5 pages — 3 if file > 6 MB), sends to vision LLM. Returns `{path, page_count, documents: [{pages, document_type, fields, summary}, ...]}`. Always an array — single-doc files yield length 1, multi-doc PDFs yield N. Read-through cache in `kit_document_parses` table — vision is called at most once per file. |
| `kit_crop_document({source_path, region, page_number?})` | Cut out a region (`voided_check_micr`, `voided_check_header`, `driver_license_top/bottom`, `ein_top`, `permit_top`, `full_page`). Stored in `crops/tg-<chat>/`, signed URL returned. Telegram channel auto-forwards crops to the chat as photos so the operator visually verifies bank fields. |

### Boarding-application CRUD
| Tool | Effect |
|---|---|
| `kit_get_application({application_id})` | GET full record. Tariff `feeSchedule.fees[]` is collapsed to a count to keep the agent's context lean. |
| `kit_overwrite_application({application_id, profile})` | PUT a fully-typed `OnboardingProfile`. Wiki defaults baked in: campaign 1579, equipment KIT POS, AMEX OptBlue=Yes, principal CEO/100%, US country (229) and nationality (199), volumes 50K/$50/$500, sales 100/0/0, building Office Building/Rents/Commercial/501-2500. ZIP auto-stripped to 5 digits. Tariff fields NEVER touched. |
| `kit_validate_application({application_id})` | GET /validate. Returns missing-field error list + the public review URL. |
| `kit_attach_document({application_id, storage_path, document_type, principal_id?})` | Upload a stored Telegram file to KIT and link as application document. **TS enum restricts `document_type` to `voided_check` (id 6) and `driver_license` (id 18)** per wiki rule — EIN, seller permit, etc. are data sources, not attachments. |
| `kit_unlink_document({application_id, attachment_id})` | DELETE a document link without removing the underlying attachment. Used to sanitise recycled test slots. |
| `kit_search_mcc({query})` | Page-scan + local filter through the MCC catalog. Returns the catalog `id` to feed into `kit_overwrite_application` — the 4-digit MCC code is NOT the id. |
| `kit_list_test_apps()` | List recent boarding apps with an `is_recycled_test_slot` flag (true when `companyName == "Test Company LLC"`). The agent picks an OLDEST `New + recycled` slot for a new merchant — never POSTs a fresh application. |

## Onboarding playbook

Triggered when the operator says "онбординг" / "onboard" /
"create application" / "enroll" after uploading documents. Agent
runs phases in order:

1. **Collect & parse.** `kit_list_session_uploads` → for each file
   `kit_parse_document` (cached). Identify what's there. Without
   voided check + driver license, STOP and report what's missing.
2. **Verification crops.** Before reporting any routing/account
   number, `kit_crop_document(path, 'voided_check_micr')`. Same
   for header (DBA/address cross-check) and DL halves
   (name/DOB/address). Telegram channel auto-forwards to chat as
   photos.
3. **Operator confirmation.** Show parsed fields + crops, wait
   for explicit "ок" / "yes" / "go" / "подтверждаю" before any
   write. `kit_list_test_apps` and pick OLDEST
   `is_recycled_test_slot && status='New'` slot.
4. **Fill.** `kit_search_mcc` to resolve catalog id (5993 → 791
   for cigar stores). `kit_get_application` to grab the existing
   `principals[0].id` and pass it back as `existing_id` so the
   record is reused, not duplicated. Then
   `kit_overwrite_application(app_id, profile)` — defaults filled
   by the tool, tariffs untouched.
5. **Attach docs.** Only `voided_check` and `driver_license`. EIN
   / seller permit / operating agreement stay as data sources.
6. **Validate + report.** `kit_validate_application` →
   Asked/Result reply with Application id, DBA, EIN, MCC,
   Address, Principal, Bank, pending fields, review URL. Final
   line: "Submit-for-underwriting is manual — open the URL,
   eyeball the form, approve in the KIT dashboard."

## Hard rules baked into system prompt

1. **Never click ACTIVATE / Submit-for-Underwriting.** Hard.
2. **Documents to attach: only DL + Voided Check.** Other docs
   are data sources, never `kit_attach_document`'d.
3. **Bank fields require a crop first.** `voided_check_micr` is
   sent to the chat before the agent reports routing/account.
4. **Update existing > create new.** Use the recycled test-app
   pool (`Test Company LLC` slots), never POST a new application.
5. **Multi-member LLC detection** via Form 1065 in the EIN
   letter. Don't blindly default ownership 100%; ASK for the
   split.
6. **Voided check holder name == EIN legal name** (case-
   insensitive). Mismatch → STOP and ask.
7. **founded_date never in the future.**
8. **Vision rate-limit graceful fail**, no blind retry; tell the
   operator quota is exhausted, offer manual entry.

## Storage

| Bucket / table | Purpose | Cleanup |
|---|---|---|
| `kit-onboarding-uploads` (Supabase Storage, private, 10 MB/file) | Documents from Telegram + crops under `crops/`. Per-thread prefix `tg-<chat_id>/` so listing is cheap and a delete is bounded. | pg_cron `kit-onboarding-uploads-cleanup` deletes objects older than 7 days, daily 03:17 UTC. |
| `kit_conversations` (Supabase) | One JSONB row per Telegram chat. Trim to 40 messages on each save. | Per-thread on `/reset`. |
| `kit_document_parses` (Supabase) | Vision-LLM output cached per storage path so a file is parsed at most once. | Per-thread on `/reset` via `clearThreadCache(threadId)`. |

## Memory + status localisation

- Conversation history is OpenAI shape (system / user / assistant
  with tool_calls / tool with tool_call_id) persisted as JSONB.
  System prompt is reapplied fresh on every run; not stored.
- Status messages and tool labels exist in two languages
  selected by `detectLang(text)` (Cyrillic → ru, else en). Each
  `KitTool` ships its own `label(args, lang)`; the channel
  adapter calls `toolLabel(name, args, lang)` and falls back to a
  humanised function name.

## Known issues / open questions

- **Vision-LLM rate limits.** Free OpenRouter pool is shared
  (≈200 req/day across all `:free` models). One naïve onboarding
  used to burn ≥ 15 req via retries; reduced to 5 (one-shot per
  model + 60 s in-process per-model cool-off). Still tight at
  scale. Today's session burnt the day's budget — expect parse
  errors until quota resets.
- **Architecture debt.** Kit currently splits text-LLM (`gpt-oss
  -120b:free`) and vision-LLM (`gemma-4-26b:free`) — two model
  calls per onboarding, twice the quota burn, plus a parsers /
  cache layer to glue them. A single multimodal-with-tools model
  (e.g. `anthropic/claude-haiku-4.5` paid, ~$0.05/onboarding, OR
  `google/gemma-4-26b-a4b-it:free` if it confirms tool calling)
  would simplify ~600 lines of code away. Decision pending —
  trade-off: free + fragile vs. paid pennies + reliable.
- **Tesseract.js fallback** as a Step-3.5 candidate for OCR
  resilience when free vision is exhausted: extract text without
  any LLM call, hand the text to the existing text agent. Not
  yet implemented.

## Cross-references

- Source repo: github.com/walklikeaman/kitpos-operator
- Boarding API rules + defaults: [`application-onboarding`](application-onboarding.md)
- File-build flow (PAX terminal provisioning): [`file-build-flow`](file-build-flow.md)
- Existing Python mini-agents that share the same KIT API but
  serve other surfaces: `agents/kit-dashboard-merchant-data/` and
  `agents/kit-dashboard-agent/` in this repo.
