"""
paxstore_v2 — reusable Playwright modules for the 2026 PAX Store admin UI.

Layered:
  field_ids   — element IDs / constants for BroadPOS Sierra parameter sub-tabs
  browser     — login, session reuse via Supabase, cookies, screenshots, navigation
  forms       — fill helpers, tab clicks, stage detection, NEXT advancement
  operations  — high-level ops: create_terminal, push_template, push_firmware,
                fill_tsys, fill_receipt, set_internal_pos_mode, activate_task

See `agents/maverick-terminal-agent/docs/PAXSTORE_AUTOMATION_V2.md` for selectors.
"""
from .browser import (  # noqa: F401
    ADMIN_URL,
    LOGIN_URL,
    SESSION_KEY,
    dismiss_cookies,
    launch_session,
    login_if_needed,
    open_terminal,
    shot,
)
from .field_ids import (  # noqa: F401
    MISC_RUNNING_MODE_ID,
    PARAMETER_TABS,
    RECEIPT_FIELD_IDS,
    TSYS_FIELD_IDS,
)
from .forms import (  # noqa: F401
    advance_until_active_task,
    click_next_once,
    click_tab_exact,
    detect_stage,
    fill_autocomplete,
    fill_text_by_id,
)
from .operations import (  # noqa: F401
    activate_pending_task,
    create_terminal,
    fill_receipt_form,
    fill_tsys_form,
    open_pending_template_task,
    push_firmware_to_terminal,
    push_template_to_terminal,
    set_internal_pos_mode,
)
