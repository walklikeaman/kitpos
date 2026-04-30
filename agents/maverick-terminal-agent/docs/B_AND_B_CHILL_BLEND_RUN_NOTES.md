# B&B Chill and Blend Live Run Notes

Merchant:

- DBA: `B&B Chill and Blend`
- Merchant Number: `201100306001`
- VAR PDF: `/Users/walklikeaman/Downloads/B&B-Chill-and-Blend-KIT-POS-VAR-Sheet.pdf`
- Derived TSYS Terminal ID Number: `76615476` from `V6615476`

Devices:

- POS: `L1400`, serial `2630132073`
- PIN pad: `A3700`, serial `2620079273`

Confirmed PAX state from live runs:

- Merchant `B&B Chill and Blend 201100306001` was created and is active.
- POS terminal `B&B Chill and Blend 2630132073` was created. PAX detected `PAX - L1400`.
- PIN pad terminal `B&B Chill and Blend 2620079273` was created. PAX detected `PAX - A3700`.
- POS firmware `Uniphiz_11.0.0_Elm_V19.1.17_20260408` was created and activated.
- KIT POS `0.202` was already present from group/default configuration.
- KIT Stock `0.40` push task was created. The run was interrupted during the activation wait; verify whether the task activated before continuing.

Not completed before stopping:

- Verify/activate KIT Stock if still pending.
- Push and activate KIT Merchant on the POS.
- Push firmware on the A3700 PIN pad.
- Push and activate KIT Back Screen on A3700.
- Push BroadPOS TSYS Sierra on A3700, load `Parameter File:retail.zip`, and fill TSYS VAR fields.
- Leave BroadPOS TSYS Sierra pending for review unless explicitly told to activate.

Automation notes:

- Headless PAX login and Terminal Management navigation work.
- PAX tables need radio/row coordinate fallback; text row clicks alone do not always select rows.
- PAX pages often remain on task detail pages after activation. Re-select the terminal and reopen `App & Firmware > Push Task` before the next app step.
- Runtime history is written locally to `tmp/run-history/paxstore_runs.jsonl`, but `tmp/` is intentionally gitignored.
