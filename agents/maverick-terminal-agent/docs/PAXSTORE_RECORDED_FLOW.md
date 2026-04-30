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

## TSYS Field Mapping

The script reads the VAR PDF first, then maps extracted VAR numbers to the recorded TSYS form fields:

| TSYS label | Recorded input id | Source |
| --- | --- | --- |
| Merchant Name | `6_tsys_F1_tsys_param_merchantName` | PDF DBA |
| Bank Identification Number | `0_tsys_F1_tsys_param_BIN` | PDF BIN |
| Agent Bank Number | `1_tsys_F1_tsys_param_agentNumber` | PDF Agent Bank |
| Agent Chain Number | `2_tsys_F1_tsys_param_chainNumber` | PDF Chain |
| Merchant Number | `3_tsys_F1_tsys_param_MID` | PDF Merchant number |
| Store Number | `4_tsys_F1_tsys_param_storeNumber` | PDF Store Number |
| Terminal Number | `5_tsys_F1_tsys_param_terminalNumber` | PDF Terminal Number |
| Merchant City | `7_tsys_F1_tsys_param_merchantCity` | PDF City |
| Merchant State | `8_tsys_F1_tsys_param_merchantState` | PDF State |
| City Code | `9_tsys_F1_tsys_param_cityCode` | PDF ZIP |
| Merchant Category Code | `13_tsys_F1_tsys_param_categoryCode` | PDF MCC |
| Time Zone Differential | `17_tsys_F1_tsys_param_timeZone` | Fixed `708-PST` |
| Terminal ID Number | `19_tsys_F1_tsys_param_TID` | Derived `V Number -> 7...` |

## Runner

Use dry-run first. Dry-run fills forms and captures screenshots, but does not click the final submit buttons.

```bash
python scripts/paxstore_provision_from_pdf.py \
  --pdf "/path/to/var-sheet.pdf" \
  --serial-number 2290653126 \
  --steps merchant,terminal
```

Execute submit clicks explicitly:

```bash
python scripts/paxstore_provision_from_pdf.py \
  --pdf "/path/to/var-sheet.pdf" \
  --serial-number 2290653126 \
  --steps merchant,terminal \
  --submit
```

Full workflow after the terminal flow is confirmed:

```bash
python scripts/paxstore_provision_from_pdf.py \
  --pdf "/path/to/var-sheet.pdf" \
  --serial-number 2290653126 \
  --steps all \
  --submit
```

Screenshots and extracted page text are written under `tmp/screenshots/`.

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
- Fill TSYS fields from the VAR PDF.
- Keep the BroadPOS TSYS Sierra task pending for review unless `--activate-payment-app` is explicitly passed.
