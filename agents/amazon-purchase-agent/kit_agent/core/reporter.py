"""
Telegram-ready report generator.

Format: short, scannable, Markdown-compatible with Telegram (MarkdownV2).
Includes check crop image paths for sending as photos.

Report sections:
  1. Header (merchant + app link)
  2. Key extracted fields
  3. Check numbers with crop image paths
  4. ⚠️ Uncertain fields (low confidence)
  5. ❌ Empty / incomplete fields found on dashboard
  6. Anything unrecognized / needs human review
"""
from __future__ import annotations
from pathlib import Path
from typing import Any


def build_telegram_report(
    profile: dict,
    app_id: int,
    verification: dict[str, Any],
    check_images: dict[str, Path] | None = None,
) -> dict:
    """
    Returns:
      {
        "text": str,          # Telegram message text (HTML mode)
        "images": [Path],     # Images to send before the text message
        "captions": [str],    # Caption per image
      }
    """
    app_url = f"https://kitdashboard.com/boarding/default/modify?id={app_id}"
    contact = profile.get("contact_person", {})
    biz = profile.get("business_address", {})
    home = profile.get("home_address", {})
    flags = profile.get("validation_flags", [])

    # --- Build the text report ---
    lines = []

    # Header
    dba = profile.get("business_name_dba", "—")
    lines += [
        f"<b>📋 {dba}</b>",
        f'<a href="{app_url}">App #{app_id}</a>',
        "",
    ]

    # Key data block
    ein = profile.get("ein", "—")
    ssn = profile.get("ssn", "")
    masked_ssn = f"***-**-{ssn[-4:]}" if len(ssn) >= 4 else "—"
    lines += [
        "<b>Данные мерчанта</b>",
        f"  Имя:     {contact.get('first','')} {contact.get('last','')}",
        f"  Тел:     {_fmt_phone(profile.get('phone',''))}",
        f"  Email:   {profile.get('email','—')}",
        f"  Бизнес:  {biz.get('street','')} {biz.get('city','')} {biz.get('state','')} {biz.get('zip','')}",
        f"  Дом:     {home.get('street','')} {home.get('city','')} {home.get('state','')} {home.get('zip','')}",
        f"  EIN:     {ein}",
        f"  SSN:     {masked_ssn}",
        f"  DOB:     {profile.get('dob','—')}",
        f"  DL#:     {profile.get('dl_number','—')}",
        "",
    ]

    # Banking
    routing = profile.get("routing_number", "—")
    account = profile.get("account_number", "—")
    bank = profile.get("bank_name", "")
    lines += [
        "<b>Банк</b>" + (f" ({bank})" if bank else ""),
        f"  Routing: <code>{routing}</code>",
        f"  Account: <code>{account}</code>",
        "",
    ]

    # Uncertain fields
    uncertain = [f for f in flags if "mismatch" in f.lower() or "low confidence" in f.lower() or "uncertain" in f.lower()]
    if uncertain:
        lines.append("⚠️ <b>Сомневаюсь — проверь:</b>")
        for u in uncertain:
            lines.append(f"  • {u}")
        lines.append("")

    # Critical flags
    critical = [f for f in flags if "critical" in f.lower() or "wrong" in f.lower() or "mismatch" in f.lower()]
    if critical:
        lines.append("🚨 <b>КРИТИЧНО:</b>")
        for c in critical:
            lines.append(f"  • {c}")
        lines.append("")

    # Verification results — empty/invalid fields per step
    empty_all = []
    invalid_all = []
    step_icons = []

    for step, result in verification.items():
        status = result.get("status", "ok")
        icon = "✅" if status == "ok" else ("⚠️" if status == "warn" else "❌")
        step_icons.append(f"{icon} {step.capitalize()}")
        empty_all.extend(result.get("empty", []))
        invalid_all.extend(result.get("invalid", []))

    lines.append("<b>Шаги приложения:</b>")
    lines.append("  " + "  ".join(step_icons))
    lines.append("")

    if invalid_all:
        lines.append("❌ <b>Ошибки (красные поля):</b>")
        for field in sorted(set(invalid_all)):
            lines.append(f"  • {field}")
        lines.append("")

    if empty_all:
        lines.append("⚠️ <b>Пустые поля:</b>")
        for field in sorted(set(empty_all)):
            lines.append(f"  • {field}")
        lines.append("")

    if not invalid_all and not empty_all and not uncertain:
        lines.append("✅ Всё заполнено, ошибок нет")
        lines.append("")

    # Footer
    lines.append(f'🔗 <a href="{app_url}">Открыть заявку #{app_id}</a>')

    text = "\n".join(lines)

    # --- Images ---
    images = []
    captions = []
    if check_images:
        if "routing" in check_images and check_images["routing"].exists():
            images.append(check_images["routing"])
            captions.append(f"🏦 Routing: <code>{routing}</code>")
        if "account" in check_images and check_images["account"].exists():
            images.append(check_images["account"])
            captions.append(f"🏦 Account: <code>{account}</code>")

    return {"text": text, "images": images, "captions": captions}


def print_telegram_report(report: dict) -> None:
    """Print the report to console (stripped of HTML tags for readability)."""
    import re
    text = report["text"]
    # Strip HTML for console
    clean = re.sub(r"<[^>]+>", "", text)
    clean = clean.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

    print("\n" + "═" * 50)
    print(clean)
    print("═" * 50)

    if report["images"]:
        print(f"\n📎 Кропы чека ({len(report['images'])} фото):")
        for img, cap in zip(report["images"], report["captions"]):
            clean_cap = re.sub(r"<[^>]+>", "", cap)
            print(f"  {img.name}  ← {clean_cap}")


def _fmt_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw or "—"
