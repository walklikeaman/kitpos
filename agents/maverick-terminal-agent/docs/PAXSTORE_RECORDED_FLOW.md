# PAX Store Recorded Flow

Source reviewed: `/Users/walklikeaman/Downloads/PAX Process.js`

## Confirmed Steps

The recording shows this sequence:

1. Log in at PAX Store auth.
2. Open Terminal Management.
3. Click Add Reseller/Merchant.
4. Select Add Merchant.
5. Fill Merchant Name.
6. Enable Activate merchant.
7. Submit the merchant dialog.
8. Add terminal from the selected merchant page.
9. Fill Terminal Name.
10. Select Immediately.
11. Fill SN.
12. Submit the terminal dialog.
13. Open App & Firmware.
14. Open Push Task.
15. Optionally push the latest firmware.
16. Push App.
17. Search `tsys`.
18. Select BroadPOS TSYS Sierra.
19. Select Parameter File:retail.zip.
20. Use the current template.
21. Open TSYS section.
22. Fill TSYS parameters.
23. Click Next.

## VAR Data Source

Preferred source is the KIT Dashboard API from
`agents/kit-dashboard-merchant-data` when `KIT_API_KEY` is configured. Use
`--var-v-number` or `--var-terminal-number` when the Merchant Number has more
than one VAR row. PDF parsing remains as a fallback via `--pdf`, Kit Dashboard
download, or email.

## TSYS Field Mapping

The script reads KIT API VAR data or the VAR PDF first, then maps extracted VAR numbers to the recorded TSYS form fields:

| TSYS label | Recorded input id | Source |
| --- | --- | --- |
| Merchant Name | `6_tsys_F1_tsys_param_merchantName` | VAR DBA |
| Bank Identification Number | `0_tsys_F1_tsys_param_BIN` | VAR BIN |
| Agent Bank Number | `1_tsys_F1_tsys_param_agentNumber` | VAR Agent Bank |
| Agent Chain Number | `2_tsys_F1_tsys_param_chainNumber` | VAR Chain |
| Merchant Number | `3_tsys_F1_tsys_param_MID` | VAR Merchant number |
| Store Number | `4_tsys_F1_tsys_param_storeNumber` | VAR Store Number |
| Terminal Number | `5_tsys_F1_tsys_param_terminalNumber` | VAR Terminal Number |
| Merchant City | `7_tsys_F1_tsys_param_merchantCity` | VAR City |
| Merchant State | `8_tsys_F1_tsys_param_merchantState` | VAR State |
| City Code | `9_tsys_F1_tsys_param_cityCode` | VAR ZIP |
| Merchant Category Code | `13_tsys_F1_tsys_param_categoryCode` | VAR MCC |
| Time Zone Differential | `17_tsys_F1_tsys_param_timeZone` | Fixed `708-PST` |
| Terminal ID Number | `19_tsys_F1_tsys_param_TID` | Derived `V Number -> 7...` |

## Runner

Use dry-run first. Dry-run fills forms and captures screenshots, but does not click the final submit buttons.

```bash
python scripts/paxstore_provision_from_pdf.py \
  --merchant-number 201100306001 \
  --var-source kit-api \
  --var-v-number V6615476 \
  --serial-number 2290653126 \
  --steps merchant,terminal
```

Execute submit clicks explicitly:

```bash
python scripts/paxstore_provision_from_pdf.py \
  --merchant-number 201100306001 \
  --var-source kit-api \
  --var-v-number V6615476 \
  --serial-number 2290653126 \
  --steps merchant,terminal \
  --submit
```

Full workflow after the terminal flow is confirmed:

```bash
python scripts/paxstore_provision_from_pdf.py \
  --merchant-number 201100306001 \
  --var-source kit-api \
  --var-v-number V6615476 \
  --serial-number 2290653126 \
  --steps all \
  --submit
```

Screenshots and extracted page text are written under `tmp/screenshots/`.

Run history is appended to `tmp/run-history/paxstore_runs.jsonl`. The history is
intentionally non-secret: it stores mode, steps, submit flags, PDF path, device
serials/models, merchant display name, derived Terminal ID Number, status, and
error text when a run fails.

## Two-Device Merchant Rules

For merchants with a POS and a PIN pad, run `--steps two-device`.

POS device:

- Create terminal as `DBA + serial number`.
- Push latest firmware before apps.
- Do not manually install KIT POS when it is already queued automatically.
- Push and activate `KIT Stock`.
- Push and activate `KIT Merchant`.

PIN pad:

- Create terminal as `DBA + serial number`.
- Push latest firmware before apps.
- Install `KIT Back Screen` only when the model requires it. Current default: `A3700`/`3700` requires it; `A35` does not.
- Push `BroadPOS TSYS Sierra`.
- Load `Parameter File:retail.zip` before filling TSYS fields.
- Fill TSYS fields from KIT API VAR data or the VAR PDF fallback.
- Keep the BroadPOS TSYS Sierra task pending for review unless `--activate-payment-app` is explicitly passed.
