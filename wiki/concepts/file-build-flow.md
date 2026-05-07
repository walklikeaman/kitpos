---
type: concept
created: 2026-05-07
updated: 2026-05-08
sources: [whatsapp-gahl-oren, session-2026-05-07-q25-a80, session-2026-05-08-rerefire]
---

# Download File Build (PAX Store + BroadPOS TSYS Sierra)

End-to-end procedure for provisioning a terminal pair on the PAX Store so that, when the merchant powers on the device, firmware + KIT apps + the TSYS payment app all install automatically. This is what "build a download file" means in the chat.

Source: PAX Store at `paxus.paxstore.us` (Terminal Management). Inputs: merchant MID + serial numbers + VAR sheet PDF.

## Step 1 — Create / locate Merchant in PAX Store

1. Terminal Management → `+` (top) → **Add Merchant**.
2. **Merchant Name** = the DBA, with the MID appended next to it. **Activate**.

## Step 2 — Add each Terminal

1. From the merchant: **+ Terminal**.
2. **Terminal Name** = `<Store DBA> <SN>`. **SN** = the serial. Set status to **Activate**.
3. The model auto-detects: **A35** is a PIN Pad (default modern set, paired with Sunmi POS), **A3700** is the Elys PIN Pad, **L1400** is the Elys POS.

## Step 3 — Push Tasks per terminal

For **every** terminal:

- **Firmware** → select the latest version → **Activate task**. Done regardless of current firmware (it's pending until the device comes online).
- **App push**:
  - **L1400 (Elys POS)** → KIT POS (auto-installs v202 by default), KIT Merchant, KIT Stock.
  - **A3700 (Elys PIN Pad)** → **KIT Back Screen** + **BroadPOS TSYS Sierra** (the payment app).
  - **A35 (modern PIN Pad)** → **only BroadPOS TSYS Sierra**. Do NOT install KIT Back Screen on A35 — only A3700.
  - **A800 standalone PIN Pad** → BroadPOS TSYS Sierra only. Also fill the **Receipt tab** (see step 5).

## Step 4 — Configure BroadPOS TSYS Sierra parameters from VAR sheet

When you push BroadPOS TSYS Sierra it asks for parameters. Use the saved template **`KIT-Android`** (works on all Android PIN Pads) to fill the common settings, then add the merchant-specific ones from the VAR sheet PDF.

VAR-sheet → BroadPOS field mapping (the order in the form does not match the VAR sheet — match by meaning):

| BroadPOS field | VAR-sheet source |
|---|---|
| BIN | BIN |
| **City Code** | **Zip code** (counter-intuitive) |
| **Category** | **MCC** |
| Time Zone | merchant's local tz (e.g. `PST`) |
| **Terminal ID** | VNumber, **but replace the leading `V` with `7`** |
| MID | from VAR sheet, NOT from the dashboard portal |

**MID gotcha**: with older accounts the VAR sheet has an extra trailing `0` on the MID compared to what shows in the portal. The VAR sheet is the source of truth for builds.

## Step 5 — Receipt tab (standalone terminals only)

If the terminal is not paired with a POS (e.g. A800, or any terminal flagged as "Stand Alone"), also fill the **Receipt** tab:

- Line 1: business name
- Line 2: business street address
- Line 3: city, state, zip (e.g. `San Francisco, CA 94103`)
- Line 4: phone number

## Step 6 — Hand off to Gahl

Leave the BroadPOS TSYS Sierra task as **Pending** (do not Activate). Gahl reviews every build before activating. Firmware and KIT-app tasks can stay activated.

## Operator-side automation status

- Browser-driven automation lives in `agents/maverick-terminal-agent` (Playwright). Headless by default with saved session. Inputs: VAR PDF + SNs.
- PAX Marketplace REST API would replace the browser flow — request was sent to PAX support on 2026-05-05; PAX confirmed it's a paid premium feature; quote pending.

## 2026 PAX UI update (rediscovered 2026-05-07)

PAX Store changed its admin UI in 2026. The original `paxstore_provision_from_pdf.py`
script (written for the prior UI) **does not work past terminal creation**. The
flow above still describes the right operator actions, but the UI navigation
is different. New v2 scripts live alongside the legacy script — see
`agents/maverick-terminal-agent/docs/PAXSTORE_AUTOMATION_V2.md` for the
selectors / IDs / Playwright details.

### Key changes in the new UI

- Apex `paxstore.us` has no DNS A record. Use `paxus.paxstore.us/admin/` and
  `auth.paxstore.us/passport/login?client_id=admin&market=paxus`.
- The old single tab "App & Firmware" is **gone**. Functionality split into:
  - Terminal Details → **Push Task** tab → sub-tabs **App / Firmware / RKI**
  - **Apps** are pushed via *Push Task → App → `+ PUSH APP`* (modal opens with App / Push Template sub-tabs)
  - **Firmware** is pushed via *Push Task → Firmware → `+ PUSH FIRMWARE`* (modal lists firmware versions, **radio buttons** not checkboxes — only one firmware per push)
  - **Templates** are pushed inside the same `+ PUSH APP` modal under the *Push Template* sub-tab (currently only `KIT-Android` exists, bundles `BroadPOS TSYS Sierra v1.03.44E_20251017`)
- Push Task Configuration has **5 stages**: Create Task → **Template** (parameter editing) → Active Task → Effective → Completed.
- During stage 2 (Template), the BroadPOS Sierra parameter editor has 13 sub-tabs:
  INDUSTRY · EDC · RECEIPT · TIP · MISC · TSYS · COMMUNICATION · CARD TYPE · BIN FILE · EMV · EXTERNAL DEVICE · POS · MULTI-MERCHANT.
  **Each click on `NEXT` (bottom-right) saves the current sub-tab and moves
  to the next.** Without `NEXT`, the data is NOT persisted server-side.
  After the last sub-tab, `NEXT` advances stage 2 → stage 3.
- Stage 3 has `PREVIOUS` (back to parameter editing) and `ACTIVATE` (commits the push).
  Per Gahl: leave BroadPOS task pending — operator clicks `ACTIVATE` after review.

### New device entries (2026-05-07)

- **PAX Q25** — small PIN Pad ("dumb") cabled to a Smart POS. **Does not run
  BroadPOS** itself. Register in PAX Store, no firmware/template push to it.
- **PAX A80** — Smart POS that the Q25 connects to. This is where firmware,
  template (KIT-Android), and TSYS parameters are pushed when the merchant
  is stand-alone (no separate cash register).

### Stand-alone vs POS-connected (Gahl's rule, 2026-05-07)

When the smart POS (A80, A800, etc.) prints receipts itself (no external POS like
Sunmi), this is a **stand-alone** configuration. In that case fill on the POS device:

1. **Receipt tab** — Header Lines 1-4 with DBA / street / city-state-zip / phone.
2. **POS tab** — switch from `External POS` to `Internal POS` (toggle inside
   the collapsed `POS INFORMATION` accordion; UI selector still TBD —
   see PAXSTORE_AUTOMATION_V2.md).

### Stage-2 form persistence — re-fire technique (verified 2026-05-08)

End-to-end click-through verified on Alshuja Market 1240490019 (A80, MID 201100308288) in BroadPOS Sierra V1.03.44E_20251017 via `claude-in-chrome` MCP. All **24 workflow fields** found by ID and successfully re-saved on **NEXT** with the green toast `App parameter saved successfully` (Stage 2 → Stage 3).

**Re-fire technique** — for each field, *no value change required*; PAX Store's React form treats this as a valid update:

```js
const setter = Object.getOwnPropertyDescriptor(
  window.HTMLInputElement.prototype, "value"
).set;
const el = document.getElementById(id);
el.focus();
setter.call(el, el.value);                                  // re-set same value via native setter
el.dispatchEvent(new Event("input",  { bubbles: true }));
el.dispatchEvent(new Event("change", { bubbles: true }));
el.blur();
```

One JS-call per sub-tab can batch all its fields in ~50 ms total. Cheaper for a headless agent than 24 separate Playwright `fill()` calls.

**Verified field IDs (2026 UI):**

| Sub-tab | Fields | Source of truth |
|---|---|---|
| RECEIPT | 5 headers + 5 trailers — `*_sys_F2_sys_cap_receiptHeader{0..4}`, `*_sys_F2_sys_cap_receiptTrailer{0..4}` | `paxstore_v2/field_ids.py:RECEIPT_FIELD_IDS` |
| TSYS | 13 — merchantName / BIN / agentNumber / chainNumber / MID / storeNumber / terminalNumber / merchantCity / merchantState* / cityCode (=ZIP) / categoryCode (=MCC) / timeZone* / TID | `paxstore_v2/field_ids.py:TSYS_FIELD_IDS` |
| MISC | 1 — `0_sys_F2_sys_cap_runningMode` (`Internal POS/Standalone` for stand-alone scenario) | `paxstore_v2/field_ids.py:MISC_RUNNING_MODE_ID` |

\* `merchantState` and `timeZone` are autocomplete inputs; native re-fire works on them too — no need to interact with the dropdown.

**Tab-switch timing:** `wait 2s` between sub-tab clicks is sufficient for the form to render. **NEXT click → result toast** in ~6s.

**Click-through order verified:** Stage 3 `PREVIOUS` → Stage 2 INDUSTRY (default) → RECEIPT → TSYS → MISC → `NEXT` → Stage 3 (Active Task), green toast.

**Note** — the user's manual click-through and this automated re-fire produced identical persistence behavior. Refactor priority B (finish stand-alone flow) ahead of A (extract helpers): the helper-module signatures should now lock around the JS-batch pattern, not Playwright's `fill_by_id` per field.

## Cross-references

- Source: [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
- Related: [kit-apps-by-device](kit-apps-by-device.md), [application-onboarding](application-onboarding.md).
- Repo: legacy `agents/maverick-terminal-agent/scripts/paxstore_provision_from_pdf.py`,
  v2 scripts `scripts/{create_terminal,push_template,push_firmware,activate_task,fill_tsys}_v2.py`,
  docs `agents/maverick-terminal-agent/docs/PAXSTORE_PROVISIONING_RULES.md` (legacy)
  + `PAXSTORE_AUTOMATION_V2.md` (new UI).
