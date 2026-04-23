from __future__ import annotations

from dataclasses import dataclass

from maverick_agent.models import MerchantRequest, RunOutcome, RunPlan, TaskField
from maverick_agent.parsers.var_pdf import VarPdfParser
from maverick_agent.services.inbox import ImapInboxClient


@dataclass(slots=True)
class ProvisioningOrchestrator:
    parser: VarPdfParser
    inbox_client: ImapInboxClient | None = None

    def build_plan(self, request: MerchantRequest) -> RunOutcome:
        pdf_path = request.pdf_path
        notes: list[str] = []

        if pdf_path is None and self.inbox_client is not None:
            attachment = self.inbox_client.find_latest_var_pdf(request.merchant_id)
            if attachment:
                pdf_path = attachment.path
                notes.append(
                    f"PDF auto-downloaded from inbox: {attachment.filename} (subject: {attachment.subject})"
                )

        if pdf_path is None:
            return RunOutcome(
                status="needs_input",
                message="No matching VAR PDF was found in inbox.",
                next_action="Attach the merchant PDF manually and rerun the command.",
            )

        payload = self.parser.parse_file(pdf_path)
        extracted = payload.fields

        extracted_merchant_reference = extracted.get("merchant_id") or extracted.get("merchant_number")
        if extracted_merchant_reference and extracted_merchant_reference != request.merchant_id:
            notes.append(
                "Warning: merchant reference extracted from PDF does not match the input merchant_id."
            )

        if payload.missing_required:
            return RunOutcome(
                status="needs_review",
                message="PDF was found, but required fields are still missing.",
                next_action=f"Validate the PDF labels or update config/field_aliases.json. Missing: {', '.join(payload.missing_required)}",
            )

        dba_name = extracted["dba_name"]
        merchant_display_name = f"{dba_name} {request.merchant_id}"
        terminal_display_name = f"{dba_name} {request.serial_number}"
        task_fields = self._build_task_fields(extracted)

        plan = RunPlan(
            merchant_display_name=merchant_display_name,
            terminal_display_name=terminal_display_name,
            merchant_id=request.merchant_id,
            serial_number=request.serial_number,
            pdf_path=pdf_path,
            extracted_fields=extracted,
            task_fields=task_fields,
            notes=notes,
        )
        return RunOutcome(
            status="ready_for_execution",
            message="Provisioning plan built successfully.",
            next_action="Wire the confirmed PAX endpoint payloads, then execute merchant creation, activation, terminal creation, and app push.",
            plan=plan,
        )

    @staticmethod
    def _build_task_fields(extracted: dict[str, str]) -> list[TaskField]:
        mapping = {
            "merchant_number": "pdf.merchant_number",
            "bin": "pdf.bin",
            "base_identification_number": "pdf.base_identification_number",
            "mcc": "pdf.mcc",
            "chain": "pdf.chain",
            "agent_bank": "pdf.agent_bank",
            "store_number": "pdf.store_number",
            "terminal_number": "pdf.terminal_number",
            "location_number": "pdf.location_number",
            "state": "pdf.state",
            "terminal_id_number": "derived.vin_to_tid",
        }
        task_fields: list[TaskField] = []
        for key, source in mapping.items():
            value = extracted.get(key)
            if value:
                task_fields.append(TaskField(key=key, value=value, source=source))

        timezone = extracted.get("timezone") or "708 PST"
        task_fields.append(TaskField(key="timezone", value=timezone, source="default_or_pdf"))
        return task_fields
