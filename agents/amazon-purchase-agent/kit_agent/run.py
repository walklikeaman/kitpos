#!/usr/bin/env python3
"""
KIT Merchant Onboarding Agent — CLI entry point.

Usage:
    python kit_agent/run.py /path/to/merchant.pdf
    python kit_agent/run.py /path/to/merchant.pdf --dry-run
    python kit_agent/run.py --batch /path/to/inbox/

The agent:
  1. Extracts merchant data from the PDF using Claude vision
  2. Validates all fields (routing, EIN, name, address)
  3. Logs into KIT Dashboard via pure HTTP (no browser)
  4. Fills all form steps with correct data
  5. Uploads documents with correct categories
  6. Writes a structured log and prints the final report

No browser required. Works headlessly on any machine.
Credentials: set KIT_EMAIL, KIT_PASSWORD, ANTHROPIC_API_KEY in .env
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from kit_agent.core.orchestrator import OnboardingOrchestrator


def main():
    parser = argparse.ArgumentParser(
        description="KIT Dashboard Merchant Onboarding Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("pdf", nargs="?", help="Path to merchant PDF")
    parser.add_argument("--batch", metavar="DIR", help="Process all PDFs in a directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Extract and validate only — do not submit to KIT Dashboard")
    args = parser.parse_args()

    if args.batch:
        _run_batch(Path(args.batch), dry_run=args.dry_run)
    elif args.pdf:
        _run_single(Path(args.pdf), dry_run=args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)


def _run_single(pdf_path: Path, dry_run: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"  KIT Onboarding Agent")
    print(f"  PDF: {pdf_path.name}")
    print(f"  Mode: {'DRY RUN (extract only)' if dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    orchestrator = OnboardingOrchestrator(pdf_path)

    if dry_run:
        # Only extract and validate — useful for testing OCR accuracy
        profile = orchestrator._step_extract()
        orchestrator._step_validate(profile)
        print("\n📋 Extracted Profile:")
        print(json.dumps(profile, indent=2, default=str))
        print("\n✅ Dry run complete. No data submitted.")
        return

    report = orchestrator.run()
    _print_report(report["merchant_onboarding_report"])


def _run_batch(inbox: Path, dry_run: bool = False) -> None:
    pdfs = list(inbox.glob("*.pdf")) + list(inbox.glob("*.PDF"))
    if not pdfs:
        print(f"No PDFs found in {inbox}")
        sys.exit(1)

    print(f"Found {len(pdfs)} PDFs to process\n")
    results = []
    for pdf in pdfs:
        print(f"\n→ Processing: {pdf.name}")
        try:
            _run_single(pdf, dry_run=dry_run)
            results.append({"pdf": pdf.name, "status": "success"})
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            results.append({"pdf": pdf.name, "status": "failed", "error": str(e)})

    print(f"\n{'='*60}")
    print(f"Batch complete: {sum(1 for r in results if r['status']=='success')}/{len(results)} succeeded")
    for r in results:
        icon = "✅" if r["status"] == "success" else "❌"
        print(f"  {icon} {r['pdf']}")


def _print_report(r: dict) -> None:
    contact = r.get("contact_person", {})
    addr = r.get("business_address", {})
    print(f"""
{'='*60}
  MERCHANT ONBOARDING REPORT
{'='*60}
  Business Name (DBA):  {r['business_name_dba']}
  Legal Name:           {r['legal_name']}
  Entity Type:          {r['entity_type']}
  Business Address:     {addr.get('street')}, {addr.get('city')}, {addr.get('state')} {addr.get('zip')}
  Contact Person:       {contact.get('first')} {contact.get('last')}
  Email / Phone:        {r['email']} / {r['phone']}
  EIN:                  {r['ein']}
  SSN (masked):         {r['ssn_masked']}
  DOB:                  {r['dob']}
  DL Number:            {r['dl_number']}
  Routing Number:       {r['routing_number']}
  Account Number:       {r['account_number']}

  Application ID:       {r['application_id']}
  Application URL:      {r['application_url']}
  Status:               {r['status']}
  Documents:            Check {r['documents_uploaded']['voided_check']}  DL {r['documents_uploaded']['driver_license']}
""")
    if r.get("validation_warnings"):
        print("  ⚠️  Warnings:")
        for w in r["validation_warnings"]:
            print(f"     - {w}")
    print("=" * 60)


if __name__ == "__main__":
    main()
