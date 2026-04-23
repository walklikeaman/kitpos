from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kit_agent.models import KitOnboardingOutcome, KitOnboardingPlan
from kit_agent.parsers.kit_documents import KitDocumentParser


@dataclass(slots=True)
class KitMerchantOnboardingOrchestrator:
    parser: KitDocumentParser

    def build_plan(self, document_paths: list[Path | str]) -> KitOnboardingOutcome:
        payload = self.parser.parse_files(document_paths)
        errors = [issue for issue in payload.issues if issue.severity == "error"]
        warnings = [issue for issue in payload.issues if issue.severity == "warning"]
        plan = KitOnboardingPlan(
            profile=payload.profile,
            application_defaults=self._application_defaults(payload.profile.industry),
            dashboard_steps=self._dashboard_steps(),
            issues=payload.issues,
        )

        if errors:
            return KitOnboardingOutcome(
                status="blocked",
                message="KIT merchant profile has validation errors.",
                next_action="Resolve the error-level validation issues before opening KIT Dashboard.",
                plan=plan,
            )
        if warnings:
            return KitOnboardingOutcome(
                status="needs_review",
                message="KIT merchant profile is usable, but has warnings that need operator review.",
                next_action="Review warnings, then run the KIT Dashboard browser agent.",
                plan=plan,
            )
        return KitOnboardingOutcome(
            status="ready_for_dashboard",
            message="KIT merchant profile passed validation.",
            next_action="Run the KIT Dashboard browser agent with the validated profile.",
            plan=plan,
        )

    @staticmethod
    def _application_defaults(industry: str) -> dict[str, str]:
        return {
            "campaign": "Kit POS InterCharge Plus",
            "equipment_used": "KIT POS",
            "equipment_provided_by": "ISO",
            "dba_same_as_legal": "NO",
            "building_type": "Office Building",
            "ownership": "Rent",
            "zoned": "Commercial",
            "size_sq_ft": "1000",
            "nationality": "United States",
            "ownership_percent": "100",
            "accept_cards": "NO",
            "monthly_volume": "50000",
            "average_ticket": "50",
            "max_ticket": "500",
            "cards_accepted": "Visa, MasterCard, Discover, Amex, PIN Debit",
            "product_industry": industry or "Grocery Store",
            "refund_policy": "No refund, no return",
            "software": "KITPOS",
            "seasonal": "No",
            "in_person": "Stop",
            "other_sales_methods": "Active",
            "customer_type": "Individual 100%",
            "customer_location": "Local 100%",
            "fulfillment_time": "24 hours",
        }

    @staticmethod
    def _dashboard_steps() -> list[str]:
        return [
            "Log in to https://kitdashboard.com using KIT_DASHBOARD_EMAIL and KIT_DASHBOARD_PASSWORD.",
            "Open Applications -> List and reuse a No Set application created by Nikita Nakonechnyi if one exists.",
            "Otherwise create a new Modern Application with campaign Kit POS InterCharge Plus.",
            "Fill Deployment, Corporate Information, DBA, Principal, Processor/Banking, Payment Information, and Business Profile sections.",
            "Validate routing number before entering account number; validate account number before continuing.",
            "Upload the voided-check PDF and driver-license PDF to the Principal record.",
            "Stop and report the exact dashboard error if any field is rejected.",
        ]


def format_kit_onboarding_report(outcome: KitOnboardingOutcome) -> str:
    if not outcome.plan:
        return f"MERCHANT ONBOARDING REPORT\n===========================\nApplication Status: {outcome.status}\n"

    profile = outcome.plan.profile
    issues = outcome.plan.issues
    warnings = [issue for issue in issues if issue.severity == "warning"]
    errors = [issue for issue in issues if issue.severity == "error"]
    compared = _comparison_summary(profile)
    missing_or_uncertain = _priority_issues(errors, warnings)
    return "\n".join(
        [
            "MERCHANT ONBOARDING REPORT",
            "===========================",
            f"Status: {outcome.status}",
            "",
            "Used For Onboarding",
            f"Business Name (DBA): {profile.business_name_dba}",
            f"Legal Name: {profile.legal_name}",
            f"Entity Type: {profile.entity_type}",
            f"Business Address: {_format_address(profile.business_address)}",
            f"Contact Person: {profile.contact_person.full_name()}",
            f"Email / Phone: {profile.email} / {profile.phone}",
            f"EIN / Tax ID: {profile.ein}",
            f"SSN (masked): {_mask(profile.ssn)}",
            f"DOB: {profile.dob}",
            f"DL Number: {profile.dl_number}",
            f"Routing Number: {profile.routing_number}",
            f"Account Number: {_mask(profile.account_number)}",
            "",
            "Compared Across Documents",
            *compared,
            "",
            "⚠️ Missing Or Uncertain",
            *missing_or_uncertain,
        ]
    )


def _format_address(address) -> str:
    return ", ".join(part for part in [address.street, address.city, address.state, address.zip] if part)


def _format_issues(issues) -> str:
    if not issues:
        return "None"
    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _comparison_summary(profile) -> list[str]:
    lines: list[str] = []
    if profile.contact_person.full_name():
        lines.append(f"- Principal name normalized for KIT form: {profile.contact_person.full_name()}")
    if profile.business_address.is_complete():
        lines.append(f"- Business address selected from permit / application: {_format_address(profile.business_address)}")
    if profile.home_address.is_complete():
        lines.append(f"- Home address selected from ID / DL: {_format_address(profile.home_address)}")
    if profile.ein:
        lines.append(f"- Tax ID / EIN selected: {profile.ein}")
    if profile.dl_number:
        lines.append(f"- Primary identity document number selected: {profile.dl_number}")
    if not lines:
        lines.append("- None")
    return lines


def _priority_issues(errors, warnings) -> list[str]:
    lines = [f"- ⚠️ {issue.field}: {issue.message}" for issue in errors]
    lines.extend(f"- ⚠️ {issue.field}: {issue.message}" for issue in warnings)
    if not lines:
        return ["- None"]
    return lines


def _mask(value: str, visible: int = 4) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return ""
    return f"{'*' * max(len(digits) - visible, 0)}{digits[-visible:]}"
