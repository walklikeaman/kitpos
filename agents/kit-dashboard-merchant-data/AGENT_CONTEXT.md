# Agent Context: KIT Dashboard Merchant Data

> This file is for AI agents. Read it to understand what this package does,
> how it was built, and how to use/extend it without breaking anything.

## What was built and why

This agent was built on **2026-04-28** in a Claude Code session. The goal:
given a KIT Merchant ID (MID) or a merchant name, log into kitdashboard.com
and return: principal name, phone, email, business address, and optionally
download the VAR PDF file.

The `kit-dashboard-agent` (sibling folder) was used as **read-only reference**
for auth patterns and Playwright setup. **Do not modify that folder.**

## Credentials & auth

- Credentials live in `.env`: `KIT_EMAIL` and `KIT_PASSWORD`
- Session is cached at `tmp/kit-merchant-state.json` (Playwright storage_state)
- 2FA bridge: agent writes `tmp/2fa_requested.txt`, external process writes
  the code to `tmp/2fa_code.txt`, agent reads it and continues (90s timeout)
- In this session: first login was done manually (browser shown to user),
  session was saved, all subsequent runs were fully headless with no 2FA

## CLI commands (all working and tested)

```bash
# Merchant info by MID
merchant by-id 201100300996

# Merchant info by name
merchant by-name "El Camino"

# Download VAR PDF by MID
merchant get-var-by-id 201100300996

# Download VAR PDF by name
merchant get-var-by-name "El Camino"

# JSON output
merchant by-id 201100300996 --json

# Debug (screenshots saved to ./debug/)
merchant by-id 201100300996 --debug

# Custom save dir for VAR
merchant get-var-by-id 201100300996 --save-dir /path/to/dir
```

## Key implementation details

### Search logic (MerchantLookupService._find_best_match_link)
- If search_term is a 12-digit MID: scan all cards in `#listViewMerchant`
  for the card containing that MID text, navigate directly to its profile URL
- Otherwise (name search): click the first `div.panel-header a` in results
- This avoids clicking a wrong card when multiple results appear

### Profile data extraction
All extraction works on the raw `body.inner_text()` of the profile page:
- Principal: `re.search(r"\bPrincipal\b[^\n]*\n\s*(?:\d+\s+)?([A-Z][a-zA-Z'-]+(?: [A-Z][a-zA-Z'-]+)+)", body)`
  Note: the profile shows `326960 Blal Alshohatee` — the number prefix must be skipped
- Phone: first `\+?1?[-.\s]?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}` match after "Phone" label
- Email: text after "Contact Email address" label
- Business address: text after "Legal Address" label (currently extracted via debug grep, not yet in MerchantResult — add if needed)

### VAR download (MerchantLookupService._click_var_download)
Three strategies, tried in order:
1. JS scan: find `<a href>` containing "var" + (download/pdf/icon)
2. CSS positional: `div:nth-of-type(7) > div > div:nth-of-type(2) a i`
   (from browser recording `Get VAR.js`, works for kitdashboard profile layout)
3. Fallback: any `<a href>` containing "var"/"pdf"/"download" in the URL

Uses `page.expect_download()` context manager — file saved to `./downloads/`.

## What is NOT yet implemented (potential next steps)

- **Business address in MerchantResult**: the address is on the profile page
  (after "Legal Address" label) but not yet returned by `by-id`/`by-name`
- **Principal home address**: not visible on the profile page; lives in the
  application/boarding form at `/boarding/default/index`
- **Batch lookup**: process a list of MIDs from a CSV file
- **Automatic 2FA via Gmail**: the bridge file mechanism is in place;
  the Gmail MCP reader is not yet wired into a background watcher

## Session outcome summary

| Task | Result |
|---|---|
| Login (first time) | Manual — user completed 2FA in open browser |
| Session persistence | ✅ Saved to `tmp/kit-merchant-state.json` |
| Lookup by MID | ✅ Tested: 201100300996, 201100306001, 201100305938 |
| Lookup by name | ✅ Tested: "El Camino" |
| VAR download by MID | ✅ Tested: 201100300996, 50110092643 |
| VAR download by name | ✅ Tested: "El Camino" |
| All subsequent runs | ✅ Fully headless, no 2FA, session reused |

## Important: do not commit

- `.env` — contains real credentials
- `tmp/` — session cookies
- `debug/` — screenshots with PII
- `downloads/` — downloaded PDFs
