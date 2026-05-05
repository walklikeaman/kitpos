# PAX Store Provisioning — Strict Rules

> **Authoritative rule set for adding merchants/terminals in PAX Store.**
> Do not improvise. Do not enrich data. Do not add fields the user did not ask for.

## Golden Rule

**Do nothing beyond what is explicitly required.** No "helpful" extras (address, phone, country/region, state, city, ZIP, merchant type, model picks, etc.) — every additional field is friction and a chance for error. The user will tell you if more is needed.

---

## 1. Create Merchant

When creating a merchant in **Terminal Management → + → Add Merchant**, fill **only one field**:

| Field | Value | Notes |
|-------|-------|-------|
| Merchant Name | `{DBA} {MID}` | e.g. `Snack Zone 201100306415` |

Then click **OK**. That's it.

❌ **Do NOT fill:**
- Login Name (Email Address)
- Contact Name
- Phone No.
- Country/Region
- State/Province
- Postal Code
- City
- Description
- Address
- Merchant Type
- "Activate merchant" checkbox

The merchant becomes selectable in the tree after OK. Existing merchants have no extra metadata in production — keep the same shape.

---

## 2. Create Terminal

When clicking **+ TERMINAL** for the merchant:

### Field Order (strict)

1. **Terminal Name** → `{DBA} {SN}` (e.g. `Snack Zone 2290661453`)
2. **Manufacturer** → `PAX`
3. **SN (Serial Number)** → enter SN FIRST
4. **Model** → **auto-detected from SN**. Do NOT pick manually.

### Why SN-first

PAX Store recognizes the device from its registered SN and fills Model automatically. Picking Model manually before SN risks a mismatch and locks the form.

### Other fields

Leave **Quantity = 1**, **Activate Terminal = Later**. Skip TID / Location / Remark unless explicitly required.

Click **OK**. Terminal page opens with auto-assigned TID.

---

## 3. Push Firmware

Path: terminal page → **Push Task** tab → **Firmware** sub-tab → **+ FIRMWARE**.

1. Select the **latest** `PayDroid_*` build for the model (top of the list, sorted by date).
2. **OK** → screen shows the firmware push config.
3. Click **ACTIVATE** → confirm dialog → **OK**.

Firmware push goes to "Effective" / waits for the terminal to come online.

---

## 4. Install BroadPOS TSYS Sierra (via Push Template)

**Do NOT search for "tsys" or pick BroadPOS TSYS Sierra by hand.** Use the Push Template flow — the template knows which app to install and which parameter file to load.

### Steps

1. Terminal page → **Push Task** tab → **App** sub-tab → **+ PUSH APP**.
2. In the "Add Push App" dialog, click **Push Template** (the second tab/button — NOT the "App" search tab).
3. The dialog lists available push templates. **Tick the checkbox** of the relevant template (e.g. the one configured to install BroadPOS TSYS Sierra with `retail.zip`).
4. Click **OK**.

The template will auto-install **BroadPOS TSYS Sierra** with the correct Parameter File. You skip:
- the manual TSYS app search
- the BroadPOS TSYS Sierra selection
- the manual `retail.zip` template pick
- any Model dropdown change in the App Detail panel — **never touch the Model dropdown**

### Recorded selectors (from `Template.js`)

```
'aria/Add App'                                          # Push App button
'aria/Push Template'                                    # second tab in dialog
'aria/[role="table"]', 'aria/[role="checkbox"]'         # template checkbox
'aria/OK'                                               # confirm
```

These are the canonical click targets — when scripting, prefer these `aria/` selectors over coordinate clicks or text searches.

---

## 5. Fill TSYS Parameters

After the Push Template step lands you on the BroadPOS TSYS Sierra parameter editor:

1. Click the **TSYS** tab (between INDUSTRY/EDC/RECEIPT/TIP/MISC/TSYS/...).
2. Fill the fields below from VAR data. Leave everything else as the template provides.

### Fields to fill (by input ID)

| Input ID | VAR field | Example |
|----------|-----------|---------|
| `0_tsys_F1_tsys_param_BIN` | `bin` | `422108` |
| `1_tsys_F1_tsys_param_agentNumber` | `agent_bank` | `081960` |
| `2_tsys_F1_tsys_param_chainNumber` | `chain` | `081960` |
| `3_tsys_F1_tsys_param_MID` | `mid` | `201100306415` |
| `4_tsys_F1_tsys_param_storeNumber` | `store_number` | `0003` |
| `5_tsys_F1_tsys_param_terminalNumber` | `terminal_number` | `7002` |
| `6_tsys_F1_tsys_param_merchantName` | `dba` | `Snack Zone` |
| `7_tsys_F1_tsys_param_merchantCity` | `city` | `San Anselmo` |
| `8_tsys_F1_tsys_param_merchantState` | `state` (autocomplete) | `California` |
| `9_tsys_F1_tsys_param_cityCode` | `zip` | `94960` |
| `13_tsys_F1_tsys_param_categoryCode` | `mcc` | `5411` |
| `17_tsys_F1_tsys_param_timeZone` | derived (autocomplete) | `708-PST` |
| `19_tsys_F1_tsys_param_TID` | derived from `v_number` | `76646683` |

### Autocomplete fields

`merchantState` and `timeZone` are autocomplete dropdowns. Type a substring (`Cali`, `pst`) → click the matching option. Cannot be set via DOM-only assignment.

### Do NOT touch

- Model dropdown in App Detail (left panel)
- Country Code (template default `United States`)
- Currency Code (`840`)
- RIID, Sharing Group, Language Indicator, Reimbursement Attribute, Application ID, Developer ID, Support Partial Approval, P2PE Mode
- Host URLs / Ports / Phones / Baudrates
- Auto Batch Mode / Times
- Merchant ABA Number, Merchant Settlement Agent Number — left untouched if template fills them; otherwise leave blank unless explicitly given

After filling, click **NEXT** at the bottom. Push task moves to "Active Task" stage.

### Activation

By default the BroadPOS TSYS Sierra push **stays Pending** (not activated). Only activate if the user explicitly says so.

---

## 6. Terminal ID Number Derivation

```
V<digits>  → 7<digits>      (V6646683 → 76646683)
<digits>   → 7<digits>      (6646683  → 76646683)
7<digits>  → unchanged
```

See `derive_terminal_id_number()` in `scripts/paxstore_provision_from_pdf.py`.

---

## 7. Single-Device (PIN pad only) Workflow

For an A35 / A3700 sent in standalone (no separate POS):

1. Create merchant (rule §1).
2. Create terminal (rule §2).
3. Push firmware (rule §3).
4. Push template → BroadPOS TSYS Sierra (rule §4).
5. Fill TSYS (rule §5).
6. Upload merchant logo to KIT Dashboard (rule §8).
7. Stop. Leave activation for the user.

**KIT Back Screen:** install only on supported PIN pad models (A3700 ✓, A35 ✗) and only when the user requests it. The template flow is preferred — if the chosen template covers Back Screen, no separate step needed.

---

## 8. Upload Merchant Logo to KIT Dashboard

After PAX Store provisioning is complete, upload the merchant logo on KIT Dashboard as the final step.

### Command

```bash
cd agents/kit-dashboard-merchant-data

# By MID (preferred)
merchant upload-logo logo.png --mid 201100306415

# By merchant name
merchant upload-logo logo.png --name "Snack Zone"

# By internal DBA ID
merchant upload-logo logo.png --internal-id 303608
```

### How it works

- `dbaId` is resolved from `merchant.dbas[0].id` via Merchant API
- Logo is uploaded via `POST https://kitdashboard.com/merchant/profile/upload-dba-logo?id=<dbaId>` (multipart/form-data, field `file`)
- Session is reused from `tmp/kit-merchant-state.json` (same session as VarDownloader); auto-login if expired

### Remove logo

```bash
merchant remove-logo --mid 201100306415
merchant remove-logo --name "Snack Zone"
```

⚠️ **Logo upload is NOT available via REST API** — only via the UI session controller (session cookie required). Do not attempt it via Bearer token.

---

## 9. VAR Row Selection — Default is First Row

When a merchant has multiple VAR rows in the KIT API (multiple terminals), **always use the first row by default** unless instructed otherwise.

```bash
# Default — uses first VAR row automatically
python3 scripts/paxstore_provision_from_pdf.py \
  --merchant-number 201100305938 \
  --var-source kit-api \
  --pinpad-serial 2290664794 ...

# Override — pick a specific row by V Number
python3 scripts/paxstore_provision_from_pdf.py \
  --merchant-number 201100305938 \
  --var-source kit-api \
  --var-v-number V6612507 \
  --pinpad-serial 2290664794 ...

# Override — pick a specific row by Terminal Number
python3 scripts/paxstore_provision_from_pdf.py \
  --merchant-number 201100305938 \
  --var-source kit-api \
  --var-terminal-number 7001 \
  --pinpad-serial 2290664794 ...
```

Only use `--var-v-number` or `--var-terminal-number` when the user explicitly specifies which terminal/row to use. Do not guess or pick a non-first row without instruction.

---

## 10. Run History — Check Before Provisioning

Every run (including plan-only and failures) is automatically appended to:

```
tmp/run-history/paxstore_runs.jsonl
```

**Before starting provisioning for any serial number, check if it was already processed:**

```bash
# Check if serial number was already provisioned successfully
grep "2290664794" tmp/run-history/paxstore_runs.jsonl | grep '"status": "success"' | grep -v '"plan_only": true'

# View all runs for a merchant
grep "201100305938" tmp/run-history/paxstore_runs.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    r = json.loads(line)
    print(r['timestamp_utc'][:16], r['status'], r.get('pinpad_serial',''), r.get('pos_serial',''), r.get('steps',[]))
"
```

**Rule:** If a serial number already has a `success` run with `submit: true` and `plan_only: false`, do not provision again — verify the state in PAX Store first and confirm with the user.

### Fields recorded per run

| Field | Description |
|-------|-------------|
| `timestamp_utc` | When the run started |
| `status` | `success` or `failure` |
| `plan_only` | `true` = dry run, no changes made |
| `submit` | `true` = final submit buttons were clicked |
| `pinpad_serial` / `pos_serial` | Device serial numbers |
| `merchant_number` | MID |
| `terminal_id_number` | Derived TID (V-number → 7-prefix) |
| `steps` | Which steps were executed |
| `error` | Error message if `status: failure` |
| `mode` | `headless` or `headed` |

---

## 11. What this overrides

These rules supersede earlier guidance in:

- `KIT_DASHBOARD_INTEGRATION.md` "Step 4: Execute in PAX portal" — Push Template replaces the manual TSYS search.
- `scripts/install_broadpos_app.py` — the `push_app()` flow that searches "tsys" and clicks BroadPOS TSYS Sierra is **legacy**. The Push Template variant is preferred. Both are kept for reference; new work uses Push Template.
- Any merchant-creation example that fills phone/address/state/city — drop those fields.
- Any terminal-creation example that picks Model before SN — invert the order.

---

## 12. Reference: Template.js

The user-recorded Puppeteer flow at `Template.js` (in `~/Downloads`) captures the exact click sequence for the Push Template path. Selectors:

| Step | Selector |
|------|----------|
| Open Push App dialog | `aria/Add App` |
| Switch to template tab | `aria/Push Template` |
| Tick template row | `aria/[role="table"] aria/[role="checkbox"]` |
| Confirm | `aria/OK` |

When automating, drive these selectors directly.
