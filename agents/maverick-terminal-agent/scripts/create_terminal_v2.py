"""
create_terminal_v2.py — register a single terminal in the new PAX Store UI.

Thin CLI wrapper over `maverick_agent.paxstore_v2.operations.create_terminal`.

Usage:
    python3 scripts/create_terminal_v2.py \
        --serial 1240490019 --model A80 \
        --merchant-mid 201100308288 --merchant-name "Alshuja Market"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

from maverick_agent.paxstore_v2 import create_terminal, launch_session

load_dotenv(PROJECT_ROOT / ".env")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--model", required=True, help="PAX model name, e.g. A80, Q25, A35")
    ap.add_argument("--merchant-mid", required=True)
    ap.add_argument("--merchant-name", default="")
    ap.add_argument("--activate-immediately", action="store_true",
                    help="Set 'Activate Terminal: Immediately' (default: Later)")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    async with launch_session(headless=not args.headed) as (_ctx, page):
        await create_terminal(
            page,
            serial=args.serial,
            model=args.model,
            merchant_mid=args.merchant_mid,
            merchant_name=args.merchant_name,
            activate_immediately=args.activate_immediately,
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
