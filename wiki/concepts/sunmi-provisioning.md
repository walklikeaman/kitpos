---
type: concept
created: 2026-05-07
updated: 2026-05-07
sources: [whatsapp-gahl-oren]
---

# Sunmi Device Provisioning

Each Sunmi POS shipped to a merchant goes through three Sunmi-side steps before it can be used as a KIT POS device.

## Step 1 — Provisioning ticket on Sunmi service desk

URL: `https://sunmi-1.atlassian.net/servicedesk/customer/portal/50/group/72/create/10180`

KIT POS **Entity ID**: `ZE2FVADC6IG5Y` (paste this in the Entity ID field).

Submit the SNs of the new devices. Format follows previous tickets — same fields each time, only the SN list changes (example batch from 2026-04-19: `DP27256E10296,DP27256E11552,DP27256E11294,DP27256E10737,DP27256E11365`).

## Step 2 — Add agent remark in Sunmi MDM

After Sunmi provisions the devices, they appear in the MDM:

URL: `https://partner.us.sunmi.com/mdm/remoteManage`

For each newly provisioned SN, edit the **Remark** field. Convention used in chat: free-text, but include at minimum the **agent name** (e.g. `Bakil`, `Abdullah`) — match the format of existing entries on other SNs as a guide. Later refined to `Agent | Store | MID` (e.g. for Pady C Store on 2026-05-05: agent `Bakil`, store name, MID).

## Step 3 — Transfer Device

Inside Sunmi MDM → **Device** menu → **Transfer Device** (lower-left). Move the device into the appropriate downstream portal/reseller. Confirm.

## Notes

- Older devices Nikita provisioned earlier may "disappear" from his Terminal Management view — Gahl moves them under the reseller / agent. This is expected, not an error.
- After Transfer Device, the SN is no longer in Nikita's MDM scope.

## Cross-references

- Source: [whatsapp-gahl-oren](../sources/whatsapp-gahl-oren.md)
- Related: [file-build-flow](file-build-flow.md) — PAX-side provisioning runs in parallel for the PIN Pad.
