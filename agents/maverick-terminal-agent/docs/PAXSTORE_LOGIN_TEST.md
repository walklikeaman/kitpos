# PAX Store Login Probe

## Status

Last verified: 2026-04-30

Result: login succeeded.

Confirmed landing page:

```text
https://paxus.paxstore.us/admin/#/welcome
```

Confirmed visible user:

```text
Nikita Nakonechnyi
```

Confirmed menu item:

```text
Terminal Management
```

## Run

Install browser support:

```bash
pip install -e '.[browser]'
python -m playwright install chromium
```

Run the login probe:

```bash
python scripts/paxstore_login_probe.py
```

The script prompts for username and password interactively. It writes screenshots
and text snapshots under `tmp/screenshots/`. It deletes `tmp/paxstore-state.json`
by default after the test so browser auth state is not left in the workspace.

Use `--keep-state` only when a follow-up browser automation step needs to reuse
the same login session.
