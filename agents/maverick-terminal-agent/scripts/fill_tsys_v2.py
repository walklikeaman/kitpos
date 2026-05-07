"""
fill_tsys_v2.py — fill BroadPOS Sierra parameters on a pending template task.

Thin CLI wrapper over `maverick_agent.paxstore_v2.operations`.
Two scenarios:

  --scenario regular       Fill TSYS only (POS-paired devices: A35+Sunmi, A3700+L1400, etc.)
  --scenario stand-alone   Fill TSYS + RECEIPT + MISC Internal POS (A80+Q25, A800)

Usage:
    python3 scripts/fill_tsys_v2.py \
        --serial 1240490019 \
        --merchant-mid 201100308288 \
        --scenario stand-alone \
        [--var-v-number V6747448] [--headed] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

from maverick_agent.paxstore_v2 import (
    advance_until_active_task,
    fill_receipt_form,
    fill_tsys_form,
    launch_session,
    open_pending_template_task,
    open_terminal,
    set_internal_pos_mode,
)
from maverick_agent.services.kit_var_api import (
    merchant_details_by_mid,
    var_rows_by_mid,
)

load_dotenv(PROJECT_ROOT / ".env")


def fetch_var_row(merchant_mid: str, v_number: str | None) -> dict:
    api_key = os.environ["KIT_API_KEY"]
    rows = var_rows_by_mid(merchant_mid, api_key)
    if not rows:
        raise RuntimeError(f"No VAR rows found for MID {merchant_mid}")
    if v_number:
        for r in rows:
            if r.get("v_number", "").lstrip("V") == v_number.lstrip("V"):
                return r
        raise RuntimeError(f"VAR row with V-number {v_number} not found")
    return rows[0]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--merchant-mid", required=True)
    ap.add_argument("--var-v-number", default="V6747448",
                    help="V Number from VAR list to use; default = V6747448")
    ap.add_argument("--scenario", choices=["regular", "stand-alone"], default="regular",
                    help="regular = TSYS only; stand-alone = TSYS + RECEIPT + MISC Internal POS")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fill fields but do not advance NEXT through stages")
    args = ap.parse_args()

    print(f"→ fetching VAR for MID {args.merchant_mid} V={args.var_v_number}")
    var = fetch_var_row(args.merchant_mid, args.var_v_number)
    print(f"  VAR: {var.get('dba')} | bin={var.get('bin')} | TID={var.get('terminal_number')}")

    merchant = None
    if args.scenario == "stand-alone":
        print("→ fetching merchant details (RECEIPT data)")
        merchant = merchant_details_by_mid(args.merchant_mid, os.environ["KIT_API_KEY"])
        if not merchant:
            raise RuntimeError(f"Merchant {args.merchant_mid} not found")
        merchant["state"] = var.get("state", "")  # state name comes from VAR
        print(f"  merchant: {merchant['dba']} @ {merchant['street']}, "
              f"{merchant['city']}, {merchant['state']} {merchant['zip']} "
              f"| phone={merchant['phone']}")

    async with launch_session(headless=not args.headed) as (_ctx, page):
        await open_terminal(page, args.serial, args.merchant_mid)
        await open_pending_template_task(page)
        # TSYS — both scenarios
        await fill_tsys_form(page, var)
        # Stand-alone — also RECEIPT + MISC Internal POS
        if args.scenario == "stand-alone":
            await fill_receipt_form(page, merchant)
            await set_internal_pos_mode(page)
        if args.dry_run:
            print("→ DRY RUN: stopping before NEXT loop")
            return 0
        await advance_until_active_task(page, debug_prefix="tsys-next")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
