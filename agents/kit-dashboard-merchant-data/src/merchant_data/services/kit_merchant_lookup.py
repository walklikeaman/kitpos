from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

from merchant_data.models import KitCredentials, MerchantResult, VarDownloadResult

MERCHANTS_URL = "https://kitdashboard.com/merchant/default/index"

# File-based 2FA bridge: Python writes a request, external process writes the code
_2FA_REQUEST_FILE = Path("tmp/2fa_requested.txt")
_2FA_CODE_FILE = Path("tmp/2fa_code.txt")


class MerchantLookupService:
    def __init__(
        self,
        credentials: KitCredentials,
        *,
        headless: bool = True,
        debug_dir: Path | None = None,
    ) -> None:
        self.credentials = credentials
        self.headless = headless
        self.debug_dir = debug_dir

    async def lookup_by_id(self, merchant_id: str) -> MerchantResult:
        return await self._lookup(search_term=merchant_id)

    async def lookup_by_name(self, name: str) -> MerchantResult:
        return await self._lookup(search_term=name)

    async def download_var_by_id(self, merchant_id: str, save_dir: Path) -> VarDownloadResult:
        return await self._download_var(search_term=merchant_id, save_dir=save_dir)

    async def download_var_by_name(self, name: str, save_dir: Path) -> VarDownloadResult:
        return await self._download_var(search_term=name, save_dir=save_dir)

    async def _lookup(self, search_term: str) -> MerchantResult:
        from playwright.async_api import async_playwright

        self.credentials.storage_state.parent.mkdir(parents=True, exist_ok=True)
        _2FA_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        _2FA_CODE_FILE.unlink(missing_ok=True)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            ctx_kwargs: dict = {"viewport": {"width": 1440, "height": 900}}
            if self.credentials.storage_state.exists():
                ctx_kwargs["storage_state"] = str(self.credentials.storage_state)
            ctx = await browser.new_context(**ctx_kwargs)
            page = await ctx.new_page()
            page.set_default_timeout(20000)

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

    async def _login(self, page) -> None:
        creds = self.credentials
        await page.goto(creds.base_url, wait_until="domcontentloaded")

        # Already logged in — session cookie was reused
        if "/merchant/" in page.url or "/reporting/" in page.url or "/boarding/" in page.url:
            return

        await _fill_first(page, ["Email", "Email Address", "Username"], creds.email)
        await _fill_first(page, ["Password"], creds.password)
        await _click_first(page, ["Sign in", "Log in", "Login"])
        await page.wait_for_timeout(3000)

        # Check if 2FA is required
        body = await page.locator("body").inner_text(timeout=8000)
        needs_2fa = (
            "verification code" in body.lower()
            or "enter verification" in body.lower()
            or "2fa" in body.lower()
        )

        if needs_2fa:
            code = await self._get_2fa_code(creds)
            await _fill_first(page, ["Verification Code", "Enter Verification Code", "Code"], code)
            await _click_first(page, ["Log In", "Login", "Verify", "Submit"])
            await page.wait_for_timeout(5000)

            body = await page.locator("body").inner_text(timeout=8000)
            if "incorrect" in body.lower() and "code" in body.lower():
                raise RuntimeError("KIT Dashboard rejected the 2FA code.")

        await self._snapshot(page, "after-login")

    async def _get_2fa_code(self, creds: KitCredentials) -> str:
        # If code already provided in credentials, use it
        if creds.verification_code:
            return creds.verification_code

        # Signal that we need a 2FA code (Claude reads Gmail and writes the code)
        _2FA_REQUEST_FILE.write_text(str(int(time.time())), encoding="utf-8")
        print("\n[2FA] Waiting for 2FA code (reading from Gmail automatically)...")

        deadline = time.time() + 90
        while time.time() < deadline:
            await asyncio.sleep(2)
            if _2FA_CODE_FILE.exists():
                code = _2FA_CODE_FILE.read_text(encoding="utf-8").strip()
                _2FA_CODE_FILE.unlink(missing_ok=True)
                _2FA_REQUEST_FILE.unlink(missing_ok=True)
                print(f"[2FA] Code received: {code}")
                return code

        raise RuntimeError("Timed out waiting for 2FA code (90s). No code was written to tmp/2fa_code.txt")

    async def _search_and_extract(self, page, search_term: str) -> MerchantResult:
        await page.goto(MERCHANTS_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await self._snapshot(page, "merchants-list")

        # Open filters panel
        filters_btn = page.locator("div.page-header button").first
        await filters_btn.click()
        await page.wait_for_timeout(800)

        # Fill search term
        search_field = page.locator("#merchantsearch-searchterm")
        await search_field.click()
        await search_field.fill("")
        await search_field.fill(search_term)
        await page.wait_for_timeout(400)

        # Apply filters
        apply_btn = page.get_by_text("Apply filters", exact=False)
        await apply_btn.click()
        await page.wait_for_timeout(3500)
        await self._snapshot(page, "search-results")

        # Check results exist
        results_container = page.locator("#listViewMerchant")
        count = await results_container.locator("div.panel-header").count()
        if count == 0:
            raise RuntimeError(f"No merchants found for: {search_term!r}")

        # Find the correct card — match by MID or take first
        target_link = await self._find_best_match_link(page, results_container, search_term)

        # Navigate to profile
        await target_link.click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)
        await self._snapshot(page, "merchant-profile")

        # Extract merchant ID from URL (internal DB id)
        url_match = re.search(r"[?&]id=(\d+)", page.url)
        internal_id = url_match.group(1) if url_match else ""

        # Get merchant name from the profile page heading (more reliable than link text)
        merchant_name = await self._get_profile_heading(page)

        # Extract MID and contact data from profile
        raw_fields = await self._extract_profile_fields(page)
        merchant_mid = self._find_merchant_mid(raw_fields) or search_term
        principal_name = self._find_principal_name(raw_fields)
        phone = self._find_phone(raw_fields)
        email = self._find_email(raw_fields)

        return MerchantResult(
            merchant_id=merchant_mid,
            merchant_name=merchant_name,
            profile_url=page.url,
            principal_name=principal_name,
            phone=phone,
            email=email,
            raw_fields={"__internal_id__": internal_id},
        )

    async def _find_best_match_link(self, page, results_container, search_term: str):
        """Find the card that contains the search_term as MID, or fall back to first."""
        # If search_term looks like a MID (all digits), find the card that has it
        if re.fullmatch(r"\d{12}", search_term):
            matched = await page.evaluate(
                """(mid) => {
                    const container = document.getElementById('listViewMerchant');
                    if (!container) return null;
                    const cards = Array.from(container.querySelectorAll('.panel-header, [class*="panel"]'));
                    for (const card of cards) {
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
                # Navigate directly to the matched profile URL
                await page.goto(matched, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                # Return a dummy object — we already navigated
                return _AlreadyNavigated()

        return results_container.locator("div.panel-header a").first

    async def _get_profile_heading(self, page) -> str:
        # Try page <title>
        title = await page.title()
        if title and title not in {"KIT Dashboard", "Merchants", ""}:
            return title.strip()
        # Try h1/h2/h3
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
        body_text = await page.locator("body").inner_text(timeout=8000)
        fields["__body__"] = body_text
        return fields

    def _find_merchant_mid(self, fields: dict[str, str]) -> str:
        body = fields.get("__body__", "")
        # MID is a 12-digit number starting with 2011003
        m = re.search(r"\b(20110\d{7})\b", body)
        return m.group(1) if m else ""

    def _find_principal_name(self, fields: dict[str, str]) -> str:
        body = fields.get("__body__", "")

        # Pattern 1: "Principal\n<optional_number> Firstname Lastname"
        m = re.search(
            r"\bPrincipal\b[^\n]*\n\s*(?:\d+\s+)?([A-Z][a-zA-Z'-]+(?: [A-Z][a-zA-Z'-]+)+)",
            body,
        )
        if m:
            return m.group(1).strip()

        # Pattern 2: labeled dict fields
        for key, value in fields.items():
            k = key.strip().lower()
            if k in {"principal name", "owner name", "contact name"}:
                return value.strip()

        # Pattern 3: First/Last name fields
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

    def _find_email(self, fields: dict[str, str]) -> str:
        email_re = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

        # Labeled fields — prefer "Contact Email"
        for key in ("Contact Email address", "Contact Email", "Email", "Principal Email", "Support Email address"):
            if key in fields:
                m = email_re.search(fields[key])
                if m:
                    return m.group(0).strip()

        # Body: find first email after "Contact Email" label
        body = fields.get("__body__", "")
        m = re.search(r"Contact Email[^\n]*\n\s*([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", body)
        if m:
            return m.group(1).strip()

        # Fallback: first email in body
        m = email_re.search(body)
        return m.group(0).strip() if m else ""

    def _find_phone(self, fields: dict[str, str]) -> str:
        phone_re = re.compile(r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")

        # Labeled fields
        for key in ("Phone", "Phone Number", "Mobile", "Cell", "Telephone", "Contact Phone"):
            if key in fields:
                m = phone_re.search(fields[key])
                if m:
                    return m.group(0).strip()

        # Body line-by-line (first phone wins)
        for line in fields.get("__body__", "").splitlines():
            m = phone_re.search(line)
            if m:
                return m.group(0).strip()

        return ""

    async def _download_var(self, search_term: str, save_dir: Path) -> VarDownloadResult:
        from playwright.async_api import async_playwright

        self.credentials.storage_state.parent.mkdir(parents=True, exist_ok=True)
        save_dir.mkdir(parents=True, exist_ok=True)
        _2FA_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        _2FA_CODE_FILE.unlink(missing_ok=True)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            ctx_kwargs: dict = {"viewport": {"width": 1440, "height": 900}}
            if self.credentials.storage_state.exists():
                ctx_kwargs["storage_state"] = str(self.credentials.storage_state)
            ctx = await browser.new_context(**ctx_kwargs)
            page = await ctx.new_page()
            page.set_default_timeout(20000)

            try:
                await self._login(page)
                await ctx.storage_state(path=str(self.credentials.storage_state))

                # Navigate to merchant profile
                await self._navigate_to_profile(page, search_term)
                await self._snapshot(page, "var-profile")

                merchant_name = await self._get_profile_heading(page)
                url_match = re.search(r"[?&]id=(\d+)", page.url)
                internal_id = url_match.group(1) if url_match else "unknown"

                # Download VAR
                saved_path = await self._click_var_download(page, save_dir, internal_id)
                await ctx.storage_state(path=str(self.credentials.storage_state))

                return VarDownloadResult(
                    merchant_name=merchant_name,
                    search_term=search_term,
                    profile_url=page.url,
                    saved_path=saved_path,
                )
            except Exception:
                await self._snapshot(page, "var-failure")
                raise
            finally:
                await browser.close()

    async def _navigate_to_profile(self, page, search_term: str) -> None:
        """Search for merchant and open their profile page."""
        await page.goto(MERCHANTS_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        filters_btn = page.locator("div.page-header button").first
        await filters_btn.click()
        await page.wait_for_timeout(800)

        search_field = page.locator("#merchantsearch-searchterm")
        await search_field.click()
        await search_field.fill(search_term)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(3500)

        results_container = page.locator("#listViewMerchant")
        count = await results_container.locator("div.panel-header").count()
        if count == 0:
            raise RuntimeError(f"No merchants found for: {search_term!r}")

        target_link = await self._find_best_match_link(page, results_container, search_term)
        await target_link.click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

    async def _click_var_download(self, page, save_dir: Path, merchant_id: str) -> Path:
        """Find and click the VAR download icon on the merchant profile page."""

        # Strategy 1: find by text "VAR" near a download link
        var_link = await page.evaluate("""() => {
            const allLinks = Array.from(document.querySelectorAll('a'));
            for (const a of allLinks) {
                const text = (a.innerText + ' ' + (a.getAttribute('title') || '') + ' ' + (a.getAttribute('href') || '')).toLowerCase();
                if (text.includes('var') && (text.includes('download') || text.includes('.pdf') || a.querySelector('i'))) {
                    return a.href;
                }
            }
            // Also look for download icons near text "VAR"
            const allEls = Array.from(document.querySelectorAll('*'));
            for (const el of allEls) {
                if (el.children.length === 0 && (el.innerText || '').trim().toUpperCase() === 'VAR') {
                    // Walk siblings/parent for a link
                    let node = el;
                    for (let i = 0; i < 5; i++) {
                        node = node.parentElement;
                        if (!node) break;
                        const link = node.querySelector('a[href]');
                        if (link) return link.href;
                    }
                }
            }
            return null;
        }""")

        if var_link:
            # Direct URL — trigger download via navigation
            async with page.expect_download(timeout=30000) as dl_info:
                await page.evaluate(f"window.location.href = {repr(var_link)}")
            download = await dl_info.value
            suggested = download.suggested_filename or f"var_{merchant_id}.pdf"
            dest = save_dir / suggested
            await download.save_as(str(dest))
            return dest

        # Strategy 2: positional selector from browser recording
        # 7th panel → second column → download icon  (matches XPath in recording)
        selectors_to_try = [
            "div:nth-of-type(7) > div > div:nth-of-type(2) a i",
            "div:nth-of-type(7) > div > div:nth-of-type(2) a",
            # Broader fallback: any download icon in profile panels
            ".panel-content a[href*='var' i] i",
            ".panel-content a[href*='.pdf'] i",
            ".panel-content a[download] i",
        ]

        for sel in selectors_to_try:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible(timeout=3000):
                    async with page.expect_download(timeout=30000) as dl_info:
                        await el.click()
                    download = await dl_info.value
                    suggested = download.suggested_filename or f"var_{merchant_id}.pdf"
                    dest = save_dir / suggested
                    await download.save_as(str(dest))
                    return dest
            except Exception:
                continue

        # Strategy 3: find all download links and pick the one in the right panel
        all_links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                href: a.href,
                text: a.innerText.trim(),
                title: a.getAttribute('title') || '',
                hasIcon: !!a.querySelector('i, svg'),
            }));
        }""")

        for link in all_links:
            href = link.get("href", "")
            if any(kw in href.lower() for kw in ["var", "document", "pdf", "report", "download"]):
                async with page.expect_download(timeout=30000) as dl_info:
                    await page.evaluate(f"window.location.href = {repr(href)}")
                download = await dl_info.value
                suggested = download.suggested_filename or f"var_{merchant_id}.pdf"
                dest = save_dir / suggested
                await download.save_as(str(dest))
                return dest

        raise RuntimeError(
            "Could not find the VAR download link on the merchant profile page. "
            "Check debug/var-profile.png for the page state."
        )

    async def _snapshot(self, page, name: str) -> None:
        if not self.debug_dir:
            return
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=self.debug_dir / f"{name}.png", full_page=True)
        except Exception:
            pass
        try:
            body = await page.locator("body").inner_text(timeout=5000)
        except Exception as exc:
            body = f"<failed: {exc}>"
        (self.debug_dir / f"{name}.txt").write_text(
            f"URL: {page.url}\n{body[:40000]}", encoding="utf-8"
        )


class _AlreadyNavigated:
    """Sentinel returned when we already navigated to the target page."""

    async def click(self) -> None:
        pass  # navigation already done


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
