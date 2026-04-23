from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kit_agent.models import Address, KitOnboardingPlan


@dataclass(slots=True)
class DashboardField:
    section: str
    label: str
    value: str
    action: str = "fill"


@dataclass(slots=True)
class KitDashboardCredentials:
    email: str
    password: str
    base_url: str = "https://kitdashboard.com/"
    storage_state: Path = Path("tmp/kit-dashboard-state.json")
    verification_code: str | None = None


def build_dashboard_fields(plan: KitOnboardingPlan) -> list[DashboardField]:
    profile = plan.profile
    defaults = plan.application_defaults
    title = "CEO" if profile.entity_type in {"Corporation", "LLC"} else "Owner"
    fields = [
        DashboardField("Create Application", "Campaign", defaults["campaign"], "select"),
        DashboardField("Deployment", "Equipment Used", defaults["equipment_used"], "select"),
        DashboardField("Deployment", "Equipment Provided By", defaults["equipment_provided_by"], "select"),
        DashboardField("Corporate Information", "Legal Name", profile.legal_name),
        DashboardField("Corporate Information", "Entity Type", profile.entity_type, "select"),
        DashboardField("Corporate Information", "Address", _format_address(profile.business_address)),
        DashboardField("Corporate Information", "ZIP", profile.business_address.zip),
        DashboardField("Corporate Information", "Founded Date", profile.founded_date),
        DashboardField("Corporate Information", "Tax ID", profile.ein),
        DashboardField("DBA", "Information same as Legal", defaults["dba_same_as_legal"], "select"),
        DashboardField("DBA", "DBA Name", profile.business_name_dba),
        DashboardField("DBA", "Address", _format_address(profile.business_address)),
        DashboardField("DBA", "Building Type", defaults["building_type"], "select"),
        DashboardField("DBA", "Ownership", defaults["ownership"], "select"),
        DashboardField("DBA", "Zoned", defaults["zoned"], "select"),
        DashboardField("DBA", "Size", defaults["size_sq_ft"]),
        DashboardField("Principal", "First Name", profile.contact_person.first),
        DashboardField("Principal", "Last Name", profile.contact_person.last),
        DashboardField("Principal", "Nationality", defaults["nationality"], "select"),
        DashboardField("Principal", "Title", title, "select"),
        DashboardField("Principal", "SSN", profile.ssn),
        DashboardField("Principal", "Date of Birth", profile.dob),
        DashboardField("Principal", "Driver License", profile.dl_number),
        DashboardField("Principal", "Home Address", _format_address(profile.home_address)),
        DashboardField("Principal", "Ownership", defaults["ownership_percent"]),
        DashboardField("Payment Information", "Accept Cards", defaults["accept_cards"], "select"),
        DashboardField("Payment Information", "Monthly Volume", defaults["monthly_volume"]),
        DashboardField("Payment Information", "Average Ticket", defaults["average_ticket"]),
        DashboardField("Payment Information", "Max Ticket", defaults["max_ticket"]),
        DashboardField("Payment Information", "Cards Accepted", defaults["cards_accepted"], "multi_select"),
        DashboardField("Payment Information", "Product/Industry", defaults["product_industry"], "select"),
        DashboardField("Payment Information", "Refund Policy", defaults["refund_policy"]),
        DashboardField("Payment Information", "Software", defaults["software"]),
        DashboardField("Business Profile", "Seasonal", defaults["seasonal"], "select"),
        DashboardField("Business Profile", "In-Person", defaults["in_person"], "select"),
        DashboardField("Business Profile", "Customer Type", defaults["customer_type"]),
        DashboardField("Business Profile", "Customer Location", defaults["customer_location"]),
        DashboardField("Business Profile", "Fulfillment Time", defaults["fulfillment_time"]),
    ]
    if profile.routing_number:
        fields.extend(
            [
                DashboardField("Processor / Banking", "Routing Number", profile.routing_number),
                DashboardField("Processor / Banking", "Validate Routing Number", "Validate", "click"),
            ]
        )
        if profile.account_number:
            fields.extend(
                [
                    DashboardField("Processor / Banking", "Account Number", profile.account_number),
                    DashboardField("Processor / Banking", "Validate Account Number", "Validate", "click"),
                ]
            )
    return fields


class KitDashboardBrowserAgent:
    def __init__(
        self,
        credentials: KitDashboardCredentials,
        *,
        headless: bool = True,
        debug_dir: Path | None = None,
        manual_login: bool = False,
    ) -> None:
        self.credentials = credentials
        self.headless = headless
        self.debug_dir = debug_dir
        self.manual_login = manual_login

    async def login(self, page) -> None:
        if self.manual_login:
            await page.goto(self.credentials.base_url, wait_until="domcontentloaded")
            await _fill_first_available(page, ["Email", "Email Address", "Username"], self.credentials.email)
            await _fill_first_available(page, ["Password"], self.credentials.password)
            await _snapshot_if_configured(page, self.debug_dir, "manual-login-start")
            await page.wait_for_function(
                "() => !location.pathname.includes('/login')",
                timeout=180000,
            )
            await page.wait_for_timeout(2500)
            await _snapshot_if_configured(page, self.debug_dir, "after-login")
            return

        await page.goto(self.credentials.base_url, wait_until="domcontentloaded")
        await _fill_first_available(page, ["Email", "Email Address", "Username"], self.credentials.email)
        await _fill_first_available(page, ["Password"], self.credentials.password)
        await _click_first_available(page, ["Sign in", "Log in", "Login"])
        await page.wait_for_timeout(2500)

        two_factor = page.get_by_text("2FA").or_(page.get_by_text("verification code")).first
        if await two_factor.count() > 0:
            if not self.credentials.verification_code:
                raise RuntimeError("KIT Dashboard requested 2FA; pass the fresh code with --verification-code.")
            await _fill_first_available(page, ["Verification Code", "Enter Verification Code", "Code"], self.credentials.verification_code)
            await _click_first_available(page, ["Log In", "Login", "Verify"])
            await page.wait_for_timeout(5000)
        await _snapshot_if_configured(page, self.debug_dir, "after-login")
        body_text = await page.locator("body").inner_text(timeout=8000)
        if "Incorrect verification code" in body_text:
            raise RuntimeError("KIT Dashboard rejected the verification code.")
        if "Enter Verification Code" in body_text and "Log into your account" in body_text:
            raise RuntimeError("KIT Dashboard is still waiting for verification code after login attempt.")

    async def execute_plan(
        self,
        plan: KitOnboardingPlan,
        *,
        application_id: str | None = None,
        modify_url: str | None = None,
    ) -> None:
        from playwright.async_api import async_playwright

        self.credentials.storage_state.parent.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.headless)
            context_kwargs = {"viewport": {"width": 1440, "height": 1000}}
            if self.credentials.storage_state.exists():
                context_kwargs["storage_state"] = str(self.credentials.storage_state)
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            page.set_default_timeout(15000)

            try:
                await self.login(page)
                await context.storage_state(path=str(self.credentials.storage_state))
                if modify_url:
                    await page.goto(modify_url, wait_until="domcontentloaded")
                    await page.wait_for_timeout(5000)
                elif application_id:
                    await _open_applications_list(page)
                    await _snapshot_if_configured(page, self.debug_dir, "applications-list")
                    await _open_existing_application(page, application_id)
                else:
                    await _open_applications_list(page)
                    await _snapshot_if_configured(page, self.debug_dir, "applications-list")
                    await _reuse_or_create_application(page)
                await _snapshot_if_configured(page, self.debug_dir, "application-edit")
                for field in build_dashboard_fields(plan):
                    await _apply_field(page, field)
                await _snapshot_if_configured(page, self.debug_dir, "after-fill")
                await context.storage_state(path=str(self.credentials.storage_state))
            except Exception:
                await _snapshot_if_configured(page, self.debug_dir, "failure")
                await context.storage_state(path=str(self.credentials.storage_state))
                raise
            finally:
                await browser.close()


async def _apply_field(page, field: DashboardField) -> None:
    if not field.value:
        return
    if field.action == "click":
        await _click_first_available(page, [field.label, field.value])
        return
    if field.action in {"select", "multi_select"}:
        try:
            await page.get_by_label(field.label).select_option(label=field.value)
            return
        except Exception:
            await _fill_first_available(page, [field.label], field.value)
            return
    await _fill_first_available(page, [field.label], field.value)


async def _fill_first_available(page, labels: list[str], value: str) -> None:
    last_error: Exception | None = None
    for label in labels:
        try:
            await page.get_by_label(label, exact=False).fill(value)
            return
        except Exception as exc:
            last_error = exc
        try:
            await page.get_by_placeholder(label, exact=False).fill(value)
            return
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not fill any field matching labels {labels!r}") from last_error


async def _click_first_available(page, names: list[str]) -> None:
    last_error: Exception | None = None
    for name in names:
        try:
            await page.get_by_role("button", name=name, exact=False).click()
            return
        except Exception as exc:
            last_error = exc
        try:
            await page.get_by_text(name, exact=False).click()
            return
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not click any control matching {names!r}") from last_error


async def _open_applications_list(page) -> None:
    origin = f"{page.url.split('/', 3)[0]}//{page.url.split('/', 3)[2]}"
    await page.goto(f"{origin}/boarding/default/index", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    body = await page.locator("body").inner_text(timeout=8000)
    if "Boarding" in body or "Application" in body or "No Set" in body or "75566" in body:
        return
    if await _click_optional(page, ["Applications", "Application"]):
        await page.wait_for_timeout(1200)
        await _click_optional(page, ["List", "Applications List", "Application List"])
        await page.wait_for_timeout(2500)
        return
    for path in ["/application", "/applications", "/application/index", "/application/list", "/applications/list"]:
        await page.goto(f"{origin}{path}", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        body = await page.locator("body").inner_text(timeout=8000)
        if "Application" in body or "No Set" in body or "75566" in body:
            return
    raise RuntimeError("Could not open Applications list by menu text or known URL paths.")


async def _click_optional(page, names: list[str]) -> bool:
    try:
        await _click_first_available(page, names)
        return True
    except RuntimeError:
        return False


async def _reuse_or_create_application(page) -> None:
    body_text = await page.locator("body").inner_text(timeout=8000)
    if "No Set" in body_text and "Nikita Nakonechnyi" in body_text:
        await _click_first_available(page, ["Edit"])
        return
    await _click_first_available(page, ["New Application"])
    await _fill_first_available(page, ["Campaign"], "KIT POS")
    await _click_first_available(page, ["Kit POS InterCharge Plus"])
    await _click_first_available(page, ["Create Modern Application"])


async def _open_existing_application(page, application_id: str) -> None:
    await _fill_search_if_available(page, application_id)
    await page.wait_for_timeout(2500)
    opened = await page.evaluate(
        """(applicationId) => {
            const rows = Array.from(document.querySelectorAll('tr, [role="row"], .row'));
            const row = rows.find((el) => (el.innerText || '').includes(applicationId));
            if (!row) return false;
            const controls = Array.from(row.querySelectorAll('button, a, [role="button"]'));
            const options = controls.find((el) => {
                const text = [
                    el.innerText,
                    el.getAttribute('aria-label'),
                    el.getAttribute('title')
                ].filter(Boolean).join(' ').trim();
                return /options|actions|more|edit|⋮|\\.\\.\\./i.test(text);
            });
            if (options) {
                options.click();
                return true;
            }
            row.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
            return true;
        }""",
        application_id,
    )
    if not opened:
        raise RuntimeError(f"Could not find application {application_id} in Applications list.")
    await page.wait_for_timeout(1500)
    try:
        await _click_first_available(page, ["Edit"])
    except RuntimeError:
        # Some tables open edit directly on double-click or Options click.
        pass
    await page.wait_for_timeout(5000)


async def _fill_search_if_available(page, value: str) -> None:
    for label in ["Search", "Filter", "Application ID", "ID"]:
        try:
            locator = page.get_by_placeholder(label, exact=False).first
            if await locator.count() and await locator.is_visible(timeout=700):
                await locator.fill(value)
                return
        except Exception:
            pass
    try:
        search = page.locator('input[type="search"], input[placeholder*="Search" i]').first
        if await search.count() and await search.is_visible(timeout=700):
            await search.fill(value)
    except Exception:
        pass


def _format_address(address: Address) -> str:
    return ", ".join(part for part in [address.street, address.city, address.state, address.zip] if part)


async def _snapshot_if_configured(page, debug_dir: Path | None, name: str) -> None:
    if not debug_dir:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    try:
        await page.screenshot(path=debug_dir / f"{name}.png", full_page=True)
    except Exception:
        pass
    try:
        body = await page.locator("body").inner_text(timeout=5000)
    except Exception as exc:
        body = f"<body text failed: {exc}>"
    (debug_dir / f"{name}.txt").write_text(f"URL: {page.url}\n{body[:40000]}", encoding="utf-8")
