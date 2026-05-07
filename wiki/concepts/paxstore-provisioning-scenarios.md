---
type: concept
created: 2026-05-07
updated: 2026-05-07
sources: [whatsapp-gahl-oren, session-2026-05-07-q25-a80]
---

# PAX Store Provisioning Scenarios

Two provisioning patterns. The choice depends on whether the merchant has a
separate cash-register POS (e.g. Sunmi tablet) running KIT POS, or the smart
PAX device prints receipts itself (stand-alone).

## Scenario A — Terminal paired with external POS (regular)

**When**: the merchant has a separate cash register (Sunmi tablet, third-party
POS, or a PAX L1400 running KIT POS). The PIN pad just handles card / PIN.

**Flow**:

1. Register every device in PAX Store (Terminal Management → `+ TERMINAL`).
2. Push **firmware** to each device — latest version, activate.
3. Push **KIT apps** per the [device matrix](kit-apps-by-device.md):
   - Sunmi / L1400 → KIT POS, KIT Merchant, KIT Stock
   - A35 / A3700 / A800 → BroadPOS TSYS Sierra (+ KIT Back Screen on A3700)
4. Push **template** `KIT-Android` (bundles BroadPOS Sierra + parameter
   defaults) to the PIN pad.
5. Inside the BroadPOS Sierra parameter editor, fill the **TSYS** sub-tab
   from the VAR sheet. Other sub-tabs use template defaults.
6. Click NEXT through all sub-tabs. Last NEXT advances to stage 3 (Active Task).
7. Leave **pending** for Gahl to review and ACTIVATE.

**Tabs to fill**: TSYS only. Receipt + POS sub-tabs use template defaults
(External POS is the default, which is correct here).

## Scenario B — Stand-alone terminal (smart POS without cash register)

**When**: the smart PAX device (A80 with Q25 cabled to it; or standalone A800)
prints receipts itself and there is no separate POS. **Gahl's rule, stated
2026-05-07**: identify the case by absence of a Sunmi/L1400 in the build.

**Flow** (everything in scenario A, plus):

5a. **TSYS** — same as scenario A.
5b. **RECEIPT** — fill Header Lines from merchant data (the device prints
    receipts, so it needs the business identity on them):
    - Header Line 1 = merchant DBA name
    - Header Line 2 = street address (line 1)
    - Header Line 3 = `<city>, <state>, <zip>`
    - Header Line 4 = phone number
    - Header Line 5 = optional (often empty)
5c. **MISC** (not POS!) — set the field `ECR-Terminal Integration Mode`
    (id `0_sys_F2_sys_cap_runningMode`) to **`Internal POS/Standalone`**.
    Default value is `External POS` which is correct for Scenario A.
    The POS sub-tab itself only has POS Name / Version / Developer of the
    paired external POS — leave blank for stand-alone.

After all three (TSYS, RECEIPT, POS Internal), click NEXT through remaining
sub-tabs to reach stage 3. Leave pending for Gahl.

## Source data mapping

| BroadPOS field | Source | API path |
|---|---|---|
| BIN | VAR sheet | `/terminal/{tid}/var-list` → `bin` |
| Agent Bank Number | VAR sheet | … → `agentBank` |
| Agent Chain Number | VAR sheet | … → `chain` |
| Merchant Number (MID) | VAR sheet (NOT portal) | … → `merchantNumber` |
| Store Number | VAR sheet | … → `storeNumber` |
| Terminal Number | VAR sheet | … → `tid` |
| Merchant Name | merchant DBA | `/merchant/{id}` → `dbas[0].name` |
| Merchant City / State / ZIP | VAR sheet | … → `address.{city,state,zip}` |
| MCC (Category Code) | VAR sheet | … → `mcc` |
| TID (V-number with leading "V" → "7") | VAR sheet | … → `backendProcessorId` |
| Time Zone | merchant local tz | derive from state |
| **Header Line 1** (Receipt) | merchant DBA | `/merchant/{id}` → `dbas[0].name` |
| **Header Line 2** (Receipt) | street | `/merchant/{id}` → `address.line1` |
| **Header Line 3** (Receipt) | city, state, zip | concat from `address.*` |
| **Header Line 4** (Receipt) | phone | `/merchant/{id}` → `phone` |

KIT-API base: `https://dashboard.maverickpayments.com/api`. Headers required
to bypass Cloudflare: `User-Agent: Mozilla/5.0`, `Referer: https://kitdashboard.com/`.

## Identifying the scenario from a build request

Telegram intent message → scenario mapping (logic to encode in N8N or in the
provisioning orchestrator):

- Two devices listed AND one is a Sunmi / L1400 → **Scenario A** (POS-paired)
- One device only AND it's a smart POS (A80 / A800) → **Scenario B** (stand-alone)
- Q25 mentioned alongside an A80 → **Scenario B** (Q25 is dumb pinpad, A80 is the smart host)
- Operator says "stand-alone" / "no POS" / "no cash register" → **Scenario B**

## Cross-references

- Operator-level flow: [file-build-flow](file-build-flow.md)
- Device specifics: [kit-apps-by-device](kit-apps-by-device.md)
- Automation specifics (selectors, IDs, scripts): [`agents/maverick-terminal-agent/docs/PAXSTORE_AUTOMATION_V2.md`](../../agents/maverick-terminal-agent/docs/PAXSTORE_AUTOMATION_V2.md)
