---
type: concept
created: 2026-05-07
updated: 2026-05-07
sources: [whatsapp-gahl-oren]
---

# DDA Update / Bank Account Change

Workflow for changing a merchant's settlement bank account. Internally called **DDA Update** (Direct Deposit Account) — that's the official ticket-name convention; "Bank Account Change Request" is the form's own title.

## Inputs

- New voided check OR an Eldon-style bank letter on bank letterhead.
- The form `BANK ACCOUNT CHANGE REQUEST.pdf` — pre-filled with the new account details. Templates in `Context/`: `_blank.pdf` (template), `_filled.pdf` (with merchant info).
- Owner signature — collected via **Docuseal** (current) or **WeSign** (earlier templates).

## Filling the form

- Two checkboxes near the top need to be ticked.
- Leave Name / Date / Signature blank when sending out for remote signature; the e-sign service supplies them.

## Ticket on KIT Dashboard

1. Open a ticket on the merchant page.
2. **Use General ticket — NOT "bank account change"**. Choosing the dedicated bank-account-change category prompts for additional info that is unnecessary here.
3. Subject: `<Merchant DBA> DDA Update`.
4. Body: brief — Gahl's standard one-liner is just "attached".
5. Upload BOTH the signed DDA form AND the bank letter (or check). Multiple uploads are fine; or merge them into one PDF.

## E-signature

### Docuseal (current — gahl@kit-pos.com / `GahlOrenKITPOS`)

- Template already exists in the account.
- Send to merchant's email on file. **Do NOT send to a `mailinator.com` address** — those links expire too fast (caught with MID City Supermarket on 2026-04-30).
- If the merchant doesn't sign, get an alternative email and re-send. Keep the Docuseal share link (e.g. `https://docuseal.com/s/<id>`) so it can be forwarded by Gahl manually if needed.

### WeSign (earlier flow)

- Account `gahloren@gmail.com` / `GahlOrenKITPOS`.
- Template-based. After signature, the signed PDF is emailed to Gahl, not downloadable from the WeSign UI.
- Used for: Golden Hour Liquor, MID City Supermarket (Apr 23 round).

## Once signed

Upload the signed PDF + the certificate (Docuseal/WeSign produces both) to the open ticket. If you used WeSign, merging the certificate and the signed form into one PDF is acceptable.

## Cross-references

- Source: [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
- Raw artefacts: `Context/BANK ACCOUNT CHANGE REQUEST*.pdf`, `Context/Audit Log - MID CITY BANK ACCOUNT CHANGE REQUEST.pdf`, `Context/Eldon Bank letter.pdf`.
