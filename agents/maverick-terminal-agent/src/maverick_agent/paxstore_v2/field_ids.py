"""Field IDs and constants for the BroadPOS Sierra parameter editor (2026 UI).

These IDs are stable across templates — they reflect BroadPOS internal field
indices, not template-specific names. Do not change without testing on a live
push.
"""
from __future__ import annotations

# 13 sub-tabs in the BroadPOS Sierra Edit Parameter view (Stage 2 / Template).
# Order matters: NEXT cycles through them in this order.
PARAMETER_TABS: list[str] = [
    "INDUSTRY", "EDC", "RECEIPT", "TIP", "MISC", "TSYS", "COMMUNICATION",
    "CARD TYPE", "BIN FILE", "EMV", "EXTERNAL DEVICE", "POS", "MULTI-MERCHANT",
]

# TSYS sub-tab — VAR-derived merchant payment processor params.
TSYS_FIELD_IDS: dict[str, str] = {
    "merchant_name":   "6_tsys_F1_tsys_param_merchantName",
    "bin":             "0_tsys_F1_tsys_param_BIN",
    "agent_number":    "1_tsys_F1_tsys_param_agentNumber",
    "chain_number":    "2_tsys_F1_tsys_param_chainNumber",
    "mid":             "3_tsys_F1_tsys_param_MID",
    "store_number":    "4_tsys_F1_tsys_param_storeNumber",
    "terminal_number": "5_tsys_F1_tsys_param_terminalNumber",
    "merchant_city":   "7_tsys_F1_tsys_param_merchantCity",
    "merchant_state":  "8_tsys_F1_tsys_param_merchantState",   # autocomplete
    "city_code":       "9_tsys_F1_tsys_param_cityCode",        # = ZIP (counter-intuitive)
    "category_code":   "13_tsys_F1_tsys_param_categoryCode",   # = MCC
    "time_zone":       "17_tsys_F1_tsys_param_timeZone",        # autocomplete
    "tid":             "19_tsys_F1_tsys_param_TID",
}

# RECEIPT sub-tab — Header lines printed by stand-alone POS devices.
RECEIPT_FIELD_IDS: dict[str, str] = {
    "header_1":        "0_sys_F2_sys_cap_receiptHeader0",
    "header_2":        "1_sys_F2_sys_cap_receiptHeader1",
    "header_3":        "2_sys_F2_sys_cap_receiptHeader2",
    "header_4":        "3_sys_F2_sys_cap_receiptHeader3",
    "header_5":        "4_sys_F2_sys_cap_receiptHeader4",
    "trailer_1":       "6_sys_F2_sys_cap_receiptTrailer0",
    "trailer_2":       "7_sys_F2_sys_cap_receiptTrailer1",
    "trailer_3":       "8_sys_F2_sys_cap_receiptTrailer2",
    "trailer_4":       "9_sys_F2_sys_cap_receiptTrailer3",
    "trailer_5":       "10_sys_F2_sys_cap_receiptTrailer4",
}

# MISC sub-tab — ECR-Terminal Integration Mode.
# Values: "External POS" (Scenario A) / "Internal POS/Standalone" (Scenario B).
MISC_RUNNING_MODE_ID: str = "0_sys_F2_sys_cap_runningMode"

# EXTERNAL DEVICE sub-tab — PIN-pad ↔ POS link.
EXTERNAL_DEVICE_FIELD_IDS: dict[str, str] = {
    "ppc_host": "0_sys_F2_sys_cap_ppc_host",   # default: t.paxstore.us
    "ppc_port": "1_sys_F2_sys_cap_ppc_port",   # default: 9080
}
