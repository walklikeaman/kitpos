from __future__ import annotations

from pathlib import Path

import importlib.util
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "paxstore_provision_from_pdf.py"
SPEC = importlib.util.spec_from_file_location("paxstore_provision_from_pdf", SCRIPT_PATH)
assert SPEC and SPEC.loader
paxstore = importlib.util.module_from_spec(SPEC)
sys.modules["paxstore_provision_from_pdf"] = paxstore
SPEC.loader.exec_module(paxstore)


def make_data() -> paxstore.PaxProvisioningData:
    return paxstore.PaxProvisioningData(
        dba_name="B&B Chill and Blend",
        merchant_number="201100306001",
        serial_number="2620079273",
        merchant_display_name="B&B Chill and Blend 201100306001",
        terminal_display_name="B&B Chill and Blend 2620079273",
        bin="422108",
        agent_bank="081960",
        chain="081960",
        store_number="0001",
        terminal_number="7000",
        city="Memphis",
        state="Tennessee",
        zip="38116",
        mcc="5993",
        terminal_id_number="76202512",
    )


def test_a3700_pinpad_gets_back_screen() -> None:
    device = paxstore.TerminalDevice("pinpad", "2620079273", "A3700")
    plan = paxstore.build_plan_summary(
        make_data(),
        var_source_path="var.pdf",
        pdf_path=Path("var.pdf"),
        pos_device=None,
        pinpad_device=device,
        steps={"pinpad-apps"},
        activate_payment_app=False,
    )

    assert plan["devices"][0]["apps"] == ["KIT Back Screen", "BroadPOS TSYS Sierra"]


def test_a35_pinpad_skips_back_screen() -> None:
    device = paxstore.TerminalDevice("pinpad", "2290653126", "A35")
    plan = paxstore.build_plan_summary(
        make_data(),
        var_source_path="var.pdf",
        pdf_path=Path("var.pdf"),
        pos_device=None,
        pinpad_device=device,
        steps={"pinpad-apps"},
        activate_payment_app=False,
    )

    assert plan["devices"][0]["apps"] == ["BroadPOS TSYS Sierra"]


def test_back_screen_can_be_overridden() -> None:
    device = paxstore.TerminalDevice("pinpad", "2290653126", "A35", install_back_screen=True)

    assert device.needs_back_screen()


def test_api_var_data_derives_terminal_id_number() -> None:
    data = paxstore.PaxProvisioningData.from_api_var(
        {
            "dba": "B&B Chill and Blend",
            "mid": "201100306001",
            "bin": "422108",
            "agent_bank": "081960",
            "chain": "081960",
            "store_number": "0001",
            "terminal_number": "7000",
            "city": "OKC",
            "state": "Oklahoma",
            "zip": "73101",
            "mcc": "5993",
            "v_number": "V6615476",
        },
        "2620079273",
    )

    assert data.terminal_id_number == "76615476"
    assert data.terminal_number == "7000"
    assert data.terminal_display_name == "B&B Chill and Blend 2620079273"
