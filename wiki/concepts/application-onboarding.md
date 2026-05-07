---
type: concept
created: 2026-05-07
updated: 2026-05-07
sources: [whatsapp-gahl-oren]
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

## Cross-references

- Source: [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
- Follow-up workflows: [file-build-flow](file-build-flow.md), [dda-update-flow](dda-update-flow.md).
- Related agent: `agents/kit-dashboard-agent` in this repo.
