"""
push_firmware_v2.py — push firmware to a terminal via Push Task → Firmware → +PUSH FIRMWARE.

Thin CLI wrapper over `maverick_agent.paxstore_v2.operations.push_firmware_to_terminal`.

If --firmware not given, the latest (first row in PAX list) is selected.

Usage:
    python3 scripts/push_firmware_v2.py \
        --serial 1240490019 \
        --merchant-mid 201100308288 \
        [--firmware "PX7A_A80_PayDroid_..."]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

from maverick_agent.paxstore_v2 import (
    launch_session,
    open_terminal,
    push_firmware_to_terminal,
)

load_dotenv(PROJECT_ROOT / ".env")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--merchant-mid", required=True)
    ap.add_argument("--firmware", help="Optional firmware name; default = latest (first row)")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    async with launch_session(headless=not args.headed) as (_ctx, page):
        await open_terminal(page, args.serial, args.merchant_mid)
        await push_firmware_to_terminal(page, firmware_name=args.firmware)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
