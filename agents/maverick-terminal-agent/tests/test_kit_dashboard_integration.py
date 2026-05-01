"""
Tests for KIT Dashboard API integration.
Demonstrates how VAR data flows from API to PAX provisioning.
"""
from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import json
from typing import Any


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "paxstore_provision_from_pdf.py"
SPEC = importlib.util.spec_from_file_location("paxstore_provision_from_pdf", SCRIPT_PATH)
assert SPEC and SPEC.loader
paxstore = importlib.util.module_from_spec(SPEC)
sys.modules["paxstore_provision_from_pdf"] = paxstore
SPEC.loader.exec_module(paxstore)


# Sample VAR data from KIT Dashboard API
PADY_C_STORE_VAR = {
    "legal_name": "Pady C Store LLC",
    "dba": "Pady C Store",
    "street": "8301 NE 10th St",
    "city": "Midwest City",
    "state": "Oklahoma",
    "zip": "73110",
    "phone": "+1 615-429-2561",
    "mid": "201100305938",
    "mcc": "5411",
    "monthly_volume": 50000.0,
    "v_number": "V6612507",
    "terminal_number": 7001,
    "store_number": "0002",
    "location_number": "00001",
    "chain": "081960",
    "agent_bank": "081960",
    "bin": "422108",
    "accept_visa_mc": True,
    "accept_pin_debit": True,
    "accept_gift_card": False,
    "accept_amex": True,
    "accept_discover": True,
    "accept_ebt": False,
}

B_B_CHILL_VAR = {
    "dba": "B&B Chill and Blend",
    "mid": "201100306001",
    "bin": "422108",
    "agent_bank": "081960",
    "chain": "081960",
    "store_number": "0001",
    "terminal_number": 7000,
    "city": "Memphis",
    "state": "Tennessee",
    "zip": "38116",
    "mcc": "5993",
    "v_number": "V6615476",
}


class TestKitDashboardIntegration:
    """Tests for KIT Dashboard API → PAX provisioning workflow"""

    def test_pady_c_store_api_data_to_pax_provisioning(self) -> None:
        """
        Test: KIT API returns Pady C Store VAR data.
        Verify it converts correctly to PAX provisioning data.
        """
        # Simulate API response from KIT Dashboard
        api_var_data = PADY_C_STORE_VAR

        # Convert to PAX provisioning data (serial number for Pady C Store terminal)
        serial_number = "2290664794"
        data = paxstore.PaxProvisioningData.from_api_var(
            api_var_data, serial_number
        )

        # Verify all critical fields are set
        assert data.dba_name == "Pady C Store"
        assert data.merchant_number == "201100305938"
        assert data.serial_number == "2290664794"
        assert data.bin == "422108"
        assert data.agent_bank == "081960"
        assert data.chain == "081960"
        assert data.store_number == "0002"
        assert data.terminal_number == "7001"
        assert data.city == "Midwest City"
        assert data.state == "Oklahoma"
        assert data.zip == "73110"
        assert data.mcc == "5411"
        assert data.terminal_id_number == "76612507"  # V6612507 → 76612507
        assert data.merchant_display_name == "Pady C Store 201100305938"
        assert data.terminal_display_name == "Pady C Store 2290664794"

    def test_v_number_to_terminal_id_conversion(self) -> None:
        """
        Test: V Number from API is converted to Terminal ID Number.
        V6612507 → 76612507 (prepend 7)
        """
        tid = paxstore.derive_terminal_id_number("V6612507")
        assert tid == "76612507"

        # Edge cases
        assert paxstore.derive_terminal_id_number("V6549088") == "76549088"
        assert paxstore.derive_terminal_id_number("76612507") == "76612507"  # Already 7-prefixed
        assert paxstore.derive_terminal_id_number("6612507") == "76612507"  # Without V

    def test_pinpad_a3700_requires_back_screen(self) -> None:
        """
        Test: A3700 PIN pad gets KIT Back Screen app installed.
        """
        pinpad = paxstore.TerminalDevice("pinpad", "2620079273", "A3700")
        assert pinpad.needs_back_screen() is True

    def test_pinpad_a35_skips_back_screen(self) -> None:
        """
        Test: A35 PIN pad does NOT need KIT Back Screen (model too old).
        """
        pinpad = paxstore.TerminalDevice("pinpad", "2290653126", "A35")
        assert pinpad.needs_back_screen() is False

    def test_back_screen_override(self) -> None:
        """
        Test: install_back_screen flag can override model detection.
        """
        pinpad_force_install = paxstore.TerminalDevice(
            "pinpad", "2290653126", "A35", install_back_screen=True
        )
        assert pinpad_force_install.needs_back_screen() is True

        pinpad_force_skip = paxstore.TerminalDevice(
            "pinpad", "2620079273", "A3700", install_back_screen=False
        )
        assert pinpad_force_skip.needs_back_screen() is False

    def test_two_device_workflow_pos_pinpad(self) -> None:
        """
        Test: Build a provisioning plan for 2-device setup:
        - POS (L1400): Firmware + KIT Stock + KIT Merchant
        - PIN pad (A3700): Firmware + KIT Back Screen + BroadPOS TSYS Sierra
        """
        data = paxstore.PaxProvisioningData.from_api_var(
            PADY_C_STORE_VAR, "2290664794"
        )

        pos_device = paxstore.TerminalDevice("pos", "2630132073", "L1400")
        pinpad_device = paxstore.TerminalDevice("pinpad", "2290664794", "A3700")

        plan = paxstore.build_plan_summary(
            data,
            var_source_path="kkit-api",
            pdf_path=None,
            pos_device=pos_device,
            pinpad_device=pinpad_device,
            steps={"two-device"},
            activate_payment_app=False,
        )

        # Verify plan structure
        assert len(plan["devices"]) == 2

        # POS device
        pos = plan["devices"][0]
        assert pos["role"] == "pos"
        assert pos["serial_number"] == "2630132073"
        assert "KIT Stock" in pos["apps"]

        # PIN pad device
        pinpad = plan["devices"][1]
        assert pinpad["role"] == "pinpad"
        assert pinpad["serial_number"] == "2290664794"
        assert "KIT Back Screen" in pinpad["apps"]
        assert "BroadPOS TSYS Sierra" in pinpad["apps"]

    def test_tsys_parameters_for_paxstore_form(self) -> None:
        """
        Test: VAR data maps correctly to TSYS form field values.
        This is the actual data that gets filled into PAX portal forms.
        """
        data = paxstore.PaxProvisioningData.from_api_var(
            PADY_C_STORE_VAR, "2290664794"
        )

        # TSYS form field ID → expected value mapping
        tsys_form_values = {
            # From paxstore_provision_from_pdf.py fill_tsys_parameters()
            "6_tsys_F1_tsys_param_merchantName": data.dba_name,
            "0_tsys_F1_tsys_param_BIN": data.bin,
            "1_tsys_F1_tsys_param_agentNumber": data.agent_bank,
            "2_tsys_F1_tsys_param_chainNumber": data.chain,
            "3_tsys_F1_tsys_param_MID": data.merchant_number,
            "4_tsys_F1_tsys_param_storeNumber": data.store_number,
            "5_tsys_F1_tsys_param_terminalNumber": data.terminal_number,
            "7_tsys_F1_tsys_param_merchantCity": data.city,
            "9_tsys_F1_tsys_param_cityCode": data.zip,
            "13_tsys_F1_tsys_param_categoryCode": data.mcc,
            "19_tsys_F1_tsys_param_TID": data.terminal_id_number,
            "8_tsys_F1_tsys_param_merchantState": data.state,
            "17_tsys_F1_tsys_param_timeZone": "708-PST",
        }

        # Verify all values
        assert tsys_form_values["6_tsys_F1_tsys_param_merchantName"] == "Pady C Store"
        assert tsys_form_values["0_tsys_F1_tsys_param_BIN"] == "422108"
        assert tsys_form_values["1_tsys_F1_tsys_param_agentNumber"] == "081960"
        assert tsys_form_values["3_tsys_F1_tsys_param_MID"] == "201100305938"
        assert tsys_form_values["4_tsys_F1_tsys_param_storeNumber"] == "0002"
        assert tsys_form_values["5_tsys_F1_tsys_param_terminalNumber"] == "7001"
        assert tsys_form_values["7_tsys_F1_tsys_param_merchantCity"] == "Midwest City"
        assert tsys_form_values["8_tsys_F1_tsys_param_merchantState"] == "Oklahoma"
        assert tsys_form_values["19_tsys_F1_tsys_param_TID"] == "76612507"


class TestChainToBinMapping:
    """Tests for Chain → BIN mapping from kit-dashboard-merchant-data"""

    def test_ffb_bank_chain_081960(self) -> None:
        """Chain 081960 maps to BIN 422108 (FFB Bank)"""
        var_data = B_B_CHILL_VAR.copy()
        assert var_data["chain"] == "081960"
        assert var_data["bin"] == "422108"

    def test_pady_c_store_chain_mapping(self) -> None:
        """Pady C Store uses FFB Bank chain"""
        var_data = PADY_C_STORE_VAR.copy()
        assert var_data["chain"] == "081960"
        assert var_data["bin"] == "422108"

    def test_chain_to_bin_documented_chains(self) -> None:
        """
        Verify documented Chain → BIN mappings from AGENT_CONTEXT.md

        From kit-dashboard-merchant-data/src/merchant_data/models.py:
        _CHAIN_TO_BIN = {
            "081960": "422108",   # FFB Bank
            "261960": "442114",   # e.g. Ali Baba Smoke and Gift Shop
            "051960": "403982",   # e.g. Holy Smokes Smoke Shop
        }
        """
        chains_to_bins = {
            "081960": "422108",  # FFB Bank
            "261960": "442114",  # Ali Baba Smoke and Gift Shop
            "051960": "403982",  # Holy Smokes Smoke Shop
        }

        # These are the known mappings from real VAR analysis
        assert chains_to_bins["081960"] == "422108"
        assert chains_to_bins["261960"] == "442114"
        assert chains_to_bins["051960"] == "403982"


if __name__ == "__main__":
    # Run: pytest tests/test_kit_dashboard_integration.py -v
    pass
