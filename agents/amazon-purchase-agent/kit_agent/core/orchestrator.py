"""
Onboarding Orchestrator — coordinates extraction → validation → form filling → upload.

The orchestrator IS the agent brain:
  - It decides which steps to run (skips completed ones from state DB)
  - It handles errors with retry and fallback logic
  - It reasons about ambiguous situations before proceeding
  - All decisions are logged for auditability

Running this headlessly requires only: Python + .env credentials.
No browser. No display. No user interaction.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from .api import KITClient, KITAPIError
from .config import get_config
from .cropper import crop_check_images
from .extractor import MerchantExtractor, ExtractionError
from .logger import SessionLogger
from .reporter import build_telegram_report, print_telegram_report
from .verifier import ApplicationVerifier
from .state import ApplicationState


class OnboardingOrchestrator:
    def __init__(self, pdf_path: str | Path):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Derive merchant name from filename for logging (before we know the real name)
        slug = self.pdf_path.stem
        self.log = SessionLogger(slug)
        self.state = ApplicationState(str(self.pdf_path))
        self.cfg = get_config()

    def run(self) -> dict:
        """
        Run the full onboarding pipeline.
        Resumes from last successful step if run again on same PDF.
        Returns final report dict.
        """
        try:
            return self._run_pipeline()
        except Exception as e:
            self.log.error(f"Fatal error: {e}")
            self.state.mark_failed(str(e))
            self.log.finalize("FAILED", self.state.get_application_id())
            raise

    def _run_pipeline(self) -> dict:
        profile = self._step_extract()
        self._step_validate(profile)
        client = self._step_login()
        app_id, token = self._step_get_or_create_application(client)
        self._step_deployment(client, app_id, token)
        self._step_business(client, app_id, token, profile)
        self._step_principal(client, app_id, token, profile)
        self._step_processing(client, app_id, token, profile)
        self._step_payment(client, app_id, token, profile)
        self._step_business_profile(client, app_id, token)
        self._step_documents(client, app_id, token)

        # Verify + report
        token = client.get_application_token(app_id)
        verification = self._step_verify(client, app_id, token)
        check_images = self._crop_check(profile)
        report = build_telegram_report(profile, app_id, verification, check_images)
        print_telegram_report(report)

        self.state.mark_complete()
        self.log.finalize("COMPLETE", app_id)
        return {"report": report, "profile": profile, "app_id": app_id}

    # ── Steps ───────────────────────────────────────────────────────────────

    def _step_extract(self) -> dict:
        if self.state.step_done("extract"):
            profile = self.state.get_profile()
            self.log.info("Resuming: extraction already done", {"merchant": profile.get("business_name_dba")})
            return profile

        self.log.step("Extract data from PDF")
        extractor = MerchantExtractor(self.log)
        profile = extractor.extract_from_pdf(self.pdf_path)
        self.state.set_profile(profile)
        self.state.complete_step("extract")
        return profile

    def _step_validate(self, profile: dict) -> None:
        self.log.step("Validate extracted data")
        flags = profile.get("validation_flags", [])
        critical = [f for f in flags if "CRITICAL" in f.upper()]

        if critical:
            self.log.error("Critical validation errors — cannot proceed", {"flags": critical})
            raise ValueError(f"Critical validation errors: {critical}")

        for flag in flags:
            self.log.warn(f"Validation: {flag}")

        if not flags:
            self.log.success("All validations passed")
        self.state.complete_step("validate")

    def _step_login(self) -> KITClient:
        self.log.step("Login to KIT Dashboard")
        creds = self.cfg.get("credentials", {})
        email = creds.get("email", "")
        password = creds.get("password", "")

        if not email or not password:
            raise ValueError("KIT_EMAIL and KIT_PASSWORD must be set in .env")

        client = KITClient(self.log)
        client.login(email, password)
        self.state.complete_step("login")
        return client

    def _step_get_or_create_application(self, client: KITClient) -> tuple[int, str]:
        app_id = self.state.get_application_id()

        if app_id and self.state.step_done("create_application"):
            self.log.info(f"Resuming existing application {app_id}")
            token = client.get_application_token(app_id)
            return app_id, token

        self.log.step("Check for orphan draft / Create application")

        # Check for leftover empty drafts before creating new one
        existing_id = client.find_existing_draft()
        if existing_id:
            self.log.info(f"Reusing existing draft application {existing_id}")
            app_id = existing_id
        else:
            # Discover campaign ID dynamically
            campaign_cfg = self.cfg["campaign"]
            campaign_id = client.get_campaign_id(
                campaign_cfg["search_query"],
                campaign_cfg["target_name"],
            )
            app_id = client.create_application(campaign_id)

        token = client.get_application_token(app_id)
        self.state.set_application_id(app_id)
        self.state.complete_step("create_application")
        return app_id, token

    def _step_deployment(self, client: KITClient, app_id: int, token: str) -> None:
        if self.state.step_done("deployment"):
            return
        self.log.step("Deployment section")
        client.submit_deployment(app_id, token)
        self.state.complete_step("deployment")

    def _step_business(self, client: KITClient, app_id: int, token: str, profile: dict) -> None:
        if self.state.step_done("business"):
            return
        self.log.step("Business / Corporate / DBA")
        client.submit_business(app_id, token, profile)
        self.state.complete_step("business")

    def _step_principal(self, client: KITClient, app_id: int, token: str, profile: dict) -> None:
        if self.state.step_done("principal"):
            return
        self.log.step("Principal information")
        client.submit_principal(app_id, token, profile)
        self.state.complete_step("principal")

    def _step_processing(self, client: KITClient, app_id: int, token: str, profile: dict) -> None:
        if self.state.step_done("processing"):
            return
        self.log.step("Processing / Banking")
        client.submit_processing(app_id, token, profile)
        self.state.complete_step("processing")

    def _step_payment(self, client: KITClient, app_id: int, token: str, profile: dict) -> None:
        if self.state.step_done("payment"):
            return
        self.log.step("Payment information")
        client.submit_payment(app_id, token, profile)
        self.state.complete_step("payment")

    def _step_business_profile(self, client: KITClient, app_id: int, token: str) -> None:
        if self.state.step_done("business_profile"):
            return
        self.log.step("Business profile")
        client.submit_business_profile(app_id, token)
        self.state.complete_step("business_profile")

    def _step_documents(self, client: KITClient, app_id: int, token: str) -> None:
        if self.state.step_done("documents"):
            return
        self.log.step("Document upload")

        doc_cats = self.cfg["document_categories"]

        # Find extracted PDF pages saved alongside source PDF
        base = self.pdf_path.parent
        stem = self.pdf_path.stem

        check_pdf = base / f"{stem}_check.pdf"
        dl_pdf = base / f"{stem}_dl.pdf"

        if check_pdf.exists():
            client.upload_document(app_id, token, check_pdf, doc_cats["voided_check"])
        else:
            self.log.warn(f"Voided check PDF not found: {check_pdf}")

        if dl_pdf.exists():
            client.upload_document(app_id, token, dl_pdf, doc_cats["driver_license"])
        else:
            self.log.warn(f"Driver license PDF not found: {dl_pdf}")

        self.state.complete_step("documents")

    def _step_verify(self, client: KITClient, app_id: int, token: str) -> dict:
        """Scan all steps for empty/invalid fields — returns verification dict."""
        verifier = ApplicationVerifier(client, self.log)
        return verifier.verify_all_steps(app_id, token)

    def _crop_check(self, profile: dict) -> dict:
        """Crop MICR line from the check PDF for the report."""
        base = self.pdf_path.parent
        stem = self.pdf_path.stem
        check_pdf = base / f"{stem}_check.pdf"
        if not check_pdf.exists():
            self.log.warn("Check PDF not found — skipping image crop")
            return {}
        try:
            out_dir = self.pdf_path.parent / f"{stem}_crops"
            return crop_check_images(
                check_pdf, out_dir,
                routing=profile.get("routing_number", ""),
                account=profile.get("account_number", ""),
            )
        except Exception as e:
            self.log.warn(f"Check crop failed: {e}")
            return {}

    # ── Legacy report (kept for backward compat) ────────────────────────────

    def _build_report(self, profile: dict, app_id: int) -> dict:
        ssn = profile.get("ssn", "")
        masked_ssn = f"***-**-{ssn[-4:]}" if len(ssn) >= 4 else "N/A"
        flags = profile.get("validation_flags", [])

        return {
            "merchant_onboarding_report": {
                "business_name_dba": profile.get("business_name_dba", ""),
                "legal_name": profile.get("legal_name", ""),
                "entity_type": profile.get("entity_type", ""),
                "business_address": profile.get("business_address", {}),
                "contact_person": profile.get("contact_person", {}),
                "email": profile.get("email", ""),
                "phone": profile.get("phone", ""),
                "ein": profile.get("ein", ""),
                "ssn_masked": masked_ssn,
                "dob": profile.get("dob", ""),
                "dl_number": profile.get("dl_number", ""),
                "routing_number": profile.get("routing_number", ""),
                "account_number": profile.get("account_number", ""),
                "application_id": app_id,
                "application_url": f"https://kitdashboard.com/boarding/default/modify?id={app_id}",
                "status": "Complete",
                "validation_warnings": flags,
                "documents_uploaded": {
                    "voided_check": "✅",
                    "driver_license": "✅",
                },
            }
        }
