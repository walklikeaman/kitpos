# PAX Store Automation — v2 (2026 UI)

This is the developer-facing companion to `wiki/concepts/file-build-flow.md`.
The legacy `paxstore_provision_from_pdf.py` was written for the pre-2026 UI
and breaks past terminal creation. The v2 scripts here use the new UI.

> Operator-facing rules (what to push to which device) live in the wiki, not here.

## URLs

- Login: `https://auth.paxstore.us/passport/login?client_id=admin&market=paxus`
- Admin: `https://paxus.paxstore.us/admin/`
- Apex `paxstore.us` has no DNS A record — do not use.

## Session reuse

Playwright `storage_state` is saved in Supabase (`agent_sessions` table) under
key `paxstore`. Logic in `src/maverick_agent/services/session_store.py`.
On each script run, load saved state into a new browser context, navigate to
admin, then check for either `#left_menu_terminal_management` (logged in) or
`input[name='username']` (logged out). Wait for selector with timeout 15s,
THEN inspect URL — `wait_until=domcontentloaded` returns before the async
redirect to auth.paxstore.us completes, so URL alone is unreliable.

PAX kicks single-session: if you log in via Playwright while the user is on
the same account in their browser, **one of you is logged out**. The error
message is "Session expired, logging in from another session...". Coordinate.

## Stage detection (Push Task Configuration)

Use inner-text scan over visible buttons (not `text-is`, which is case-strict):

```python
async def detect_stage(page):
    cands = page.locator("button")
    seen = set()
    for i in range(await cands.count()):
        btn = cands.nth(i)
        if not await btn.is_visible():
            continue
        seen.add((await btn.inner_text()).strip().upper())
    if "ACTIVATE" in seen: return "active-task"   # stage 3
    if "NEXT"     in seen: return "edit-parameter" # stage 2
    return "unknown"
```

The 5 stages (visible at top of `Push Task Configuration` page):

1. Create Task — auto when push_template_v2.py / push_firmware_v2.py finishes
2. Template — parameter editor (13 sub-tabs in BroadPOS Sierra)
3. Active Task — `PREVIOUS` / `ACTIVATE` buttons
4. Effective — after operator clicks ACTIVATE; pushed to device
5. Completed — terminal applied successfully

## Tab structure inside stage 2 (BroadPOS Sierra Edit Parameter)

13 tabs, exact-text inner_text:

```
INDUSTRY · EDC · RECEIPT · TIP · MISC · TSYS · COMMUNICATION ·
CARD TYPE · BIN FILE · EMV · EXTERNAL DEVICE · POS · MULTI-MERCHANT
```

To click a tab, scan all `button` elements for one whose stripped inner_text
equals the tab name AND `is_visible()` (the left sidebar has overlapping names
like "App List" / "Firmware List" — must filter by visibility region or by
checking the button is inside the parameter editor pane).

### Bottom action buttons (always present in stage 2)

`ONLY PUSH APP` (text link) · `SAVE AS TEMPLATE` (text link) · `SAVE` (green
pill button) · `NEXT` (green pill button).

**Critical**: `button:has-text('SAVE')` matches `SAVE AS TEMPLATE` because of
substring containment, opening the wrong dialog. Always use exact inner_text
equality (strip + upper-compare).

`NEXT` saves the current sub-tab AND advances to the next sub-tab in order.
Without `NEXT`, the sub-tab's data is **not** persisted server-side.

## Field IDs

These IDs are stable across templates (they reflect BroadPOS internal field
indices). Use `page.locator(f'[id="{id}"]').fill(value)`.

### TSYS sub-tab

| Field | id |
|---|---|
| Bank Identification Number (BIN) | `0_tsys_F1_tsys_param_BIN` |
| Agent Bank Number | `1_tsys_F1_tsys_param_agentNumber` |
| Agent Chain Number | `2_tsys_F1_tsys_param_chainNumber` |
| Merchant Number (MID) | `3_tsys_F1_tsys_param_MID` |
| Store Number | `4_tsys_F1_tsys_param_storeNumber` |
| Terminal Number | `5_tsys_F1_tsys_param_terminalNumber` |
| Merchant Name | `6_tsys_F1_tsys_param_merchantName` |
| Merchant City | `7_tsys_F1_tsys_param_merchantCity` |
| Merchant State (autocomplete) | `8_tsys_F1_tsys_param_merchantState` |
| City Code (= ZIP, counter-intuitive) | `9_tsys_F1_tsys_param_cityCode` |
| Country Code (autocomplete) | `10_tsys_F1_tsys_param_countryCode` |
| Category Code (= MCC) | `13_tsys_F1_tsys_param_categoryCode` |
| Time Zone (autocomplete: type "pst" then pick "708-PST") | `17_tsys_F1_tsys_param_timeZone` |
| Terminal ID (= V-number with leading "V" replaced by "7") | `19_tsys_F1_tsys_param_TID` |

State / Time Zone / Country Code are autocomplete combos. Type a query (e.g.
first 2 chars of state, "pst" for timezone), wait ~800ms, click the popup
option whose text equals the full value.

### RECEIPT sub-tab

| Field | id |
|---|---|
| Header Line 1 (DBA) | `0_sys_F2_sys_cap_receiptHeader0` |
| Header Line 2 (street) | `1_sys_F2_sys_cap_receiptHeader1` |
| Header Line 3 (city, state, zip) | `2_sys_F2_sys_cap_receiptHeader2` |
| Header Line 4 (phone) | `3_sys_F2_sys_cap_receiptHeader3` |
| Header Line 5 (optional) | `4_sys_F2_sys_cap_receiptHeader4` |
| Trailer Lines 1–5 | `6_sys_F2_sys_cap_receiptTrailer0` … `10_..._receiptTrailer4` |
| Pre-Print toggle | `0_sys_F2_sys_cap_prePrint` (Enabled/Disabled) |

### EXTERNAL DEVICE sub-tab (PIN-pad ↔ POS link)

| Field | id | Default |
|---|---|---|
| PPC IP | `0_sys_F2_sys_cap_ppc_host` | `t.paxstore.us` |
| PPC Port | `1_sys_F2_sys_cap_ppc_port` | `9080` |

### POS sub-tab

| Field | id |
|---|---|
| POS Name | `0_sys_F4_sys_cap_posName` |
| POS Version | `1_sys_F4_sys_cap_posVersion` |
| POS Developer | `2_sys_F4_sys_cap_posDeveloper` |

These three fields live in the `POS INFORMATION` accordion. To expand the
accordion, click any element with `aria-expanded="false"` on this tab (or click
the `POS INFORMATION` header text directly). They describe the external POS
that the PIN pad is paired with — **leave blank for stand-alone**.

### MISC sub-tab — ECR-Terminal Integration Mode (the actual stand-alone toggle)

The "External POS vs Internal POS" toggle that Gahl mentions is **NOT on the
POS tab** — it's on the **MISC** tab, named `ECR-Terminal Integration Mode`.

| Field | id | Values |
|---|---|---|
| ECR-Terminal Integration Mode | `0_sys_F2_sys_cap_runningMode` | `External POS` (default for paired) / `Internal POS/Standalone` (for stand-alone) |

For Scenario B (stand-alone, e.g. A80+Q25), set to `Internal POS/Standalone`.
For Scenario A (paired), leave default `External POS`.

## v2 scripts (in scripts/)

| Script | What it does |
|---|---|
| `create_terminal_v2.py` | Register a terminal in PAX (any model). Args: `--serial --model --merchant-mid --merchant-name`. |
| `push_template_v2.py` | Push Template (default `KIT-Android`) to existing terminal. Lands on stage 2 with parameter editor open on TSYS. |
| `push_firmware_v2.py` | Push latest firmware to existing terminal (radio-button selection — only one firmware per push, NOT checkbox). |
| `activate_task_v2.py` | Click the pending task card → ACTIVATE. Skip if Gahl wants to review first. |
| `fill_tsys_v2.py` | Fill TSYS sub-tab from KIT-API VAR data; click NEXT through tabs until stage 3 reached; **does not click ACTIVATE**. |
| `explore_template_v2.py` | Read-only: enumerate every parameter sub-tab and dump field IDs / values for debug. |

All scripts share the same login/cookies/Supabase-session helpers (current
duplication — should be factored out into `src/maverick_agent/paxstore_v2/`
when the patterns stabilize).

## Open problem — NEXT did NOT advance the form (root cause unknown)

When `fill_tsys_v2.py` fills the TSYS sub-tab and clicks `NEXT` (button #71,
exact inner_text "NEXT"), nothing visibly changes — the page state appears to
stay on the same sub-tab. Ten consecutive NEXT clicks during the 2026-05-07
session did not advance to stage 3.

The user (operator) on the same task, in their browser, **could** click NEXT
and reach stage 3. So the difference is between Playwright clicks and human
clicks, not the button itself. The data is on the server now because **the
operator filled and clicked NEXT manually**, NOT because the script's NEXT
worked. Earlier I incorrectly concluded the script's NEXT had worked because
TSYS values were on the server — that conclusion was wrong; the operator
explicitly stated they re-filled and clicked NEXT to unblock the work.

Hypotheses to test next session:

1. **Required-field validation across all 13 sub-tabs** — PAX may silently
   reject NEXT until ALL tabs have valid values (not just TSYS). The operator
   filled RECEIPT + POS Internal manually before NEXT succeeded. This would
   imply: fill EVERY required field across all relevant tabs, then NEXT.
2. **Click timing** — `await loc.click(timeout=5000)` may fire before SPA
   listeners attach. Try `dispatchEvent('mousedown'+'mouseup'+'click')` or
   `click(force=True)` or wait for the button's enabled state to flip.
3. **Stale modal in DOM** — earlier session triggered a "Save As Template"
   modal that may have left a hidden overlay. Force-close any open dialogs
   before clicking NEXT.
4. **CAPTCHA / bot detection** — Cloudflare in front of paxstore.us may
   silently flag headless Chromium. Try with `--headed` to compare.

Until this is resolved, the v2 pipeline cannot be fully end-to-end. The
operator must currently click NEXT manually after `fill_tsys_v2.py` finishes.

## Known issues / TODO

- [ ] **NEXT click does not advance form** (see "Open problem" above) — main blocker.
- [ ] POS Internal / External toggle — locator unknown, accordion didn't expand.
- [ ] `fill_tsys_v2.py` only fills TSYS. For stand-alone (Gahl's rule for A80/A800)
      it must also fill RECEIPT (from KIT API merchant address) and switch POS
      to Internal.
- [ ] Helpers duplicated across 6 scripts — extract `paxstore_v2/session.py`,
      `paxstore_v2/navigation.py`, `paxstore_v2/forms.py`.
- [ ] No retry on "Session expired, logging in from another session" — should
      delete saved session + re-login fresh.
- [ ] Server (`server.py`) still calls legacy `paxstore_provision_from_pdf.py`
      via subprocess. Needs new `/provision-v2` endpoint that orchestrates the
      v2 scripts in sequence.

## Cross-references

- Wiki: [`wiki/concepts/file-build-flow.md`](../../../wiki/concepts/file-build-flow.md)
- Legacy doc: [`PAXSTORE_PROVISIONING_RULES.md`](PAXSTORE_PROVISIONING_RULES.md)
- N8N integration: [`N8N_INTEGRATION.md`](N8N_INTEGRATION.md)
