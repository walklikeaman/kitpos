"""
KIT Dashboard merchant lookup service.
Ported from github.com/walklikeaman/kitpos/agents/kit-dashboard-merchant-data.
Extended with address extraction.
"""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

from kit.models import KitCredentials, MerchantResult

MERCHANTS_URL = "https://kitdashboard.com/merchant/default/index"

_2FA_REQUEST_FILE = Path("tmp/2fa_requested.txt")
_2FA_CODE_FILE    = Path("tmp/2fa_code.txt")


class MerchantLookupService:
    def __init__(
        self,
        credentials: KitCredentials,
        *,
        headless: bool = True,
        debug_dir: Path | None = None,
    ) -> None:
        self.credentials = credentials
        self.headless    = headless
        self.debug_dir   = debug_dir

    # ── Public API ──────────────────────────────────────────────────────

    async def lookup_by_id(self, merchant_id: str) -> MerchantResult:
        return await self._lookup(search_term=merchant_id)

    async def lookup_by_name(self, name: str) -> MerchantResult:
        return await self._lookup(search_term=name)

    # ── Core flow ────────────────────────────────────────────────────────

    async def _lookup(self, search_term: str) -> MerchantResult:
        from playwright.async_api import async_playwright

        self.credentials.storage_state.parent.mkdir(parents=True, exist_ok=True)
        _2FA_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        _2FA_CODE_FILE.unlink(missing_ok=True)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx_kwargs: dict = {"viewport": {"width": 1440, "height": 900}}
            if self.credentials.storage_state.exists():
                ctx_kwargs["storage_state"] = str(self.credentials.storage_state)
            ctx = await browser.new_context(**ctx_kwargs)
            page = await ctx.new_page()
            page.set_default_timeout(20_000)

            try:
                await self._login(page)
                await ctx.storage_state(path=str(self.credentials.storage_state))
                result = await self._search_and_extract(page, search_term)
                await ctx.storage_state(path=str(self.credentials.storage_state))
                return result
            except Exception:
                await self._snapshot(page, "failure")
                raise
            finally:
                await browser.close()

    # ── Login ────────────────────────────────────────────────────────────

    async def _login(self, page) -> None:
        creds = self.credentials
        await page.goto(creds.base_url, wait_until="domcontentloaded")

        # Already logged in — session cookie was reused
        if any(s in page.url for s in ("/merchant/", "/reporting/", "/boarding/")):
            print("  ✓ KIT session valid (cookie reused)")
            return

        print("  Filling KIT login form...")
        await _fill_first(page, ["Email", "Email Address", "Username"], creds.email)
        await _fill_first(page, ["Password"], creds.password)
        await _click_first(page, ["Sign in", "Log in", "Login"])
        await page.wait_for_timeout(3_000)

        # 2FA check
        body = await page.locator("body").inner_text(timeout=8_000)
        needs_2fa = any(kw in body.lower() for kw in ("verification code", "enter verification", "2fa"))

        if needs_2fa:
            code = await self._get_2fa_code(creds)
            await _fill_first(page, ["Verification Code", "Enter Verification Code", "Code"], code)
            await _click_first(page, ["Log In", "Login", "Verify", "Submit"])
            await page.wait_for_timeout(5_000)
            body = await page.locator("body").inner_text(timeout=8_000)
            if "incorrect" in body.lower() and "code" in body.lower():
                raise RuntimeError("KIT Dashboard rejected the 2FA code.")

        await self._snapshot(page, "after-login")
        print(f"  ✓ KIT login done — {page.url[:80]}")

    async def _get_2fa_code(self, creds: KitCredentials) -> str:
        if creds.verification_code:
            return creds.verification_code

        _2FA_REQUEST_FILE.write_text(str(int(time.time())), encoding="utf-8")
        print("\n[2FA] Waiting for 2FA code (write to tmp/2fa_code.txt)...")

        deadline = time.time() + 90
        while time.time() < deadline:
            await asyncio.sleep(2)
            if _2FA_CODE_FILE.exists():
                code = _2FA_CODE_FILE.read_text(encoding="utf-8").strip()
                _2FA_CODE_FILE.unlink(missing_ok=True)
                _2FA_REQUEST_FILE.unlink(missing_ok=True)
                print(f"[2FA] Code received: {code}")
                return code

        raise RuntimeError("Timed out waiting for 2FA code (90s).")

    # ── Search + extract ─────────────────────────────────────────────────

    async def _search_and_extract(self, page, search_term: str) -> MerchantResult:
        await page.goto(MERCHANTS_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2_000)
        await self._snapshot(page, "merchants-list")

        # Open filters panel
        filters_btn = page.locator("div.page-header button").first
        await filters_btn.click()
        await page.wait_for_timeout(800)

        search_field = page.locator("#merchantsearch-searchterm")
        await search_field.click()
        await search_field.fill("")
        await search_field.fill(search_term)
        await page.wait_for_timeout(400)

        apply_btn = page.get_by_text("Apply filters", exact=False)
        await apply_btn.click()
        await page.wait_for_timeout(3_500)
        await self._snapshot(page, "search-results")

        results_container = page.locator("#listViewMerchant")
        count = await results_container.locator("div.panel-header").count()
        if count == 0:
            raise RuntimeError(f"No merchants found for: {search_term!r}")

        target_link = await self._find_best_match_link(page, results_container, search_term)
        await target_link.click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3_000)
        await self._snapshot(page, "merchant-profile")

        url_match   = re.search(r"[?&]id=(\d+)", page.url)
        internal_id = url_match.group(1) if url_match else ""

        merchant_name = await self._get_profile_heading(page)
        raw_fields    = await self._extract_profile_fields(page)

        merchant_mid   = self._find_merchant_mid(raw_fields) or search_term
        principal_name = self._find_principal_name(raw_fields)
        phone          = self._find_phone(raw_fields)
        email          = self._find_email(raw_fields)
        address        = self._find_address(raw_fields)

        return MerchantResult(
            merchant_id    = merchant_mid,
            merchant_name  = merchant_name,
            profile_url    = page.url,
            principal_name = principal_name,
            phone          = phone,
            email          = email,
            address        = address,
            raw_fields     = {"__internal_id__": internal_id},
        )

    async def _find_best_match_link(self, page, results_container, search_term: str):
        if re.fullmatch(r"\d{12}", search_term):
            matched = await page.evaluate(
                """(mid) => {
                    const container = document.getElementById('listViewMerchant');
                    if (!container) return null;
                    for (const card of Array.from(container.querySelectorAll('.panel-header, [class*="panel"]'))) {
                        if ((card.innerText || '').includes(mid)) {
                            const link = card.querySelector('a');
                            if (link) return link.href;
                        }
                    }
                    return null;
                }""",
                search_term,
            )
            if matched:
                await page.goto(matched, wait_until="domcontentloaded")
                await page.wait_for_timeout(2_000)
                return _AlreadyNavigated()

        return results_container.locator("div.panel-header a").first

    async def _get_profile_heading(self, page) -> str:
        title = await page.title()
        if title and title not in {"KIT Dashboard", "Merchants", ""}:
            return title.strip()
        for selector in ["h1", "h2", "h3", ".page-title", ".merchant-name"]:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    text = (await el.inner_text()).strip()
                    if text:
                        return text
            except Exception:
                pass
        return ""

    async def _extract_profile_fields(self, page) -> dict[str, str]:
        raw = await page.evaluate("""() => {
            const result = {};
            document.querySelectorAll('dt, .field-label').forEach(dt => {
                const label = dt.innerText.trim();
                const dd = dt.nextElementSibling;
                if (label && dd) result[label] = dd.innerText.trim();
            });
            document.querySelectorAll('tr').forEach(tr => {
                const cells = tr.querySelectorAll('td, th');
                if (cells.length >= 2) {
                    const label = cells[0].innerText.trim();
                    const value = cells[1].innerText.trim();
                    if (label) result[label] = value;
                }
            });
            document.querySelectorAll('.form-group, .field-group, .info-row').forEach(group => {
                const labelEl = group.querySelector('label, .label, strong, b');
                const valueEl = group.querySelector('input, span, p, .value');
                if (labelEl && valueEl) {
                    const label = labelEl.innerText.trim();
                    const value = valueEl.value || valueEl.innerText.trim();
                    if (label && value) result[label] = value;
                }
            });
            return result;
        }""")
        fields: dict[str, str] = dict(raw)
        body_text = await page.locator("body").inner_text(timeout=8_000)
        fields["__body__"] = body_text
        return fields

    # ── Field extractors ─────────────────────────────────────────────────

    def _find_merchant_mid(self, fields: dict[str, str]) -> str:
        body = fields.get("__body__", "")
        m = re.search(r"\b(20110\d{7})\b", body)
        return m.group(1) if m else ""

    def _find_principal_name(self, fields: dict[str, str]) -> str:
        body = fields.get("__body__", "")
        m = re.search(
            r"\bPrincipal\b[^\n]*\n\s*(?:\d+\s+)?([A-Z][a-zA-Z'-]+(?: [A-Z][a-zA-Z'-]+)+)",
            body,
        )
        if m:
            return m.group(1).strip()
        for key, value in fields.items():
            k = key.strip().lower()
            if k in {"principal name", "owner name", "contact name"}:
                return value.strip()
        first = last = ""
        for key, value in fields.items():
            k = key.strip().lower()
            if "first" in k and "name" in k and not first:
                first = value.strip()
            elif "last" in k and "name" in k and not last:
                last = value.strip()
        if first or last:
            return f"{first} {last}".strip()
        return ""

    def _find_phone(self, fields: dict[str, str]) -> str:
        phone_re = re.compile(r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")
        for key in ("Phone", "Phone Number", "Mobile", "Cell", "Telephone", "Contact Phone"):
            if key in fields:
                m = phone_re.search(fields[key])
                if m:
                    return m.group(0).strip()
        for line in fields.get("__body__", "").splitlines():
            m = phone_re.search(line)
            if m:
                return m.group(0).strip()
        return ""

    def _find_email(self, fields: dict[str, str]) -> str:
        email_re = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
        for key in ("Contact Email address", "Contact Email", "Email", "Principal Email"):
            if key in fields:
                m = email_re.search(fields[key])
                if m:
                    return m.group(0).strip()
        body = fields.get("__body__", "")
        m = re.search(r"Contact Email[^\n]*\n\s*([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", body)
        if m:
            return m.group(1).strip()
        m = email_re.search(body)
        return m.group(0).strip() if m else ""

    def _find_address(self, fields: dict[str, str]) -> str:
        """
        Extract the merchant's physical/business address.
        Tries labeled fields first, then regex patterns in body text.
        Returns a single-line address string like '123 Main St, City, ST 12345'.
        KIT Dashboard uses "Legal Address" / "DBA Address" labels.
        """
        # 1. KIT-specific and general labeled dict keys (priority order)
        for key in (
            "Legal Address", "DBA Address",
            "Business Address", "Physical Address",
            "Street Address", "Mailing Address", "Address", "Location",
        ):
            if key in fields and fields[key].strip():
                val = fields[key].strip()
                # Remove trailing ", USA" / ", US"
                val = re.sub(r",?\s*USA?\s*$", "", val, flags=re.IGNORECASE).strip()
                return _normalize_address(val)

        body = fields.get("__body__", "")

        # 2. "Legal Address" / "DBA Address" label in body text
        for label in ("Legal Address", "DBA Address", "Business Address"):
            m = re.search(
                rf"\b{re.escape(label)}\b[^\n]*\n\s*(\d+[^\n]{{5,100}})",
                body,
            )
            if m:
                raw = m.group(1).replace("\n", ", ").strip()
                raw = re.sub(r",?\s*USA?\s*$", "", raw, flags=re.IGNORECASE).strip()
                return _normalize_address(raw)

        # 3. Generic address in body — handles both "OK 73703" and "OK, 73703"
        m = re.search(
            r"(\d+\s+[A-Za-z0-9 .#/,-]{5,80},\s*[A-Za-z ]{2,30},\s*[A-Z]{2}[,\s]+\d{5}(?:-\d{4})?)",
            body,
        )
        if m:
            raw = re.sub(r",?\s*USA?\s*$", "", m.group(1), flags=re.IGNORECASE).strip()
            return _normalize_address(raw)

        return ""

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _snapshot(self, page, name: str) -> None:
        if not self.debug_dir:
            return
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=self.debug_dir / f"{name}.png", full_page=True)
        except Exception:
            pass
        try:
            body = await page.locator("body").inner_text(timeout=5_000)
        except Exception as exc:
            body = f"<failed: {exc}>"
        (self.debug_dir / f"{name}.txt").write_text(
            f"URL: {page.url}\n{body[:40_000]}", encoding="utf-8"
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalize_address(raw: str) -> str:
    """Collapse whitespace / newlines into a clean single-line address."""
    return re.sub(r"\s+", " ", raw.replace("\n", ", ")).strip(" ,")


class _AlreadyNavigated:
    async def click(self) -> None:
        pass


async def _fill_first(page, labels: list[str], value: str) -> None:
    last_exc: Exception | None = None
    for label in labels:
        for fn in (
            lambda lb=label: page.get_by_label(lb, exact=False).fill(value),
            lambda lb=label: page.get_by_placeholder(lb, exact=False).fill(value),
        ):
            try:
                await fn()
                return
            except Exception as exc:
                last_exc = exc
    raise RuntimeError(f"Could not fill any field matching {labels!r}") from last_exc


async def _click_first(page, names: list[str]) -> None:
    last_exc: Exception | None = None
    for name in names:
        for fn in (
            lambda n=name: page.get_by_role("button", name=n, exact=False).click(),
            lambda n=name: page.get_by_text(n, exact=False).click(),
        ):
            try:
                await fn()
                return
            except Exception as exc:
                last_exc = exc
    raise RuntimeError(f"Could not click any control matching {names!r}") from last_exc
