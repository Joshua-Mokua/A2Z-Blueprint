"""utils/channels/swift.py — SWIFT MT cross-border messaging simulator.

Covers MT103 (single customer credit transfer), MT202 (general financial
institution transfer), MT940 (statement). Realistic SWIFT FIN traffic
shape — minutes to hours for correspondent settlement.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
import uuid

from utils.channels.base import (
    BaseChannelSimulator, ChannelStatus, ChannelRequest,
)


class SwiftSimulator(BaseChannelSimulator):
    """Simulator for SWIFT MT messages (FIN)."""

    channel_name = "swift"

    # SWIFT correspondent traffic — much higher latency than RTGS
    latency_p50_ms = 120_000.0     # 2 minutes
    latency_p99_ms = 3_600_000.0   # 1 hour

    failure_modes = {
        ChannelStatus.FAILED_SANCTIONS_HIT: 0.012,
        ChannelStatus.FAILED_BENEFICIARY_REJECT: 0.015,
        ChannelStatus.FAILED_INSUFFICIENT_FUNDS: 0.003,
        ChannelStatus.FAILED_TIMEOUT: 0.002,
        ChannelStatus.FAILED_HOST_UNAVAILABLE: 0.003,
        ChannelStatus.FAILED_INVALID_PAYLOAD: 0.005,
    }

    VALID_MT_TYPES = {"103", "202", "202COV", "910", "940", "950"}

    def validate_payload(self, payload: Dict[str, Any]) -> tuple:
        mt_type = str(payload.get("mt_type") or "").strip()
        if mt_type not in self.VALID_MT_TYPES:
            return False, (
                f"unsupported mt_type {mt_type!r}; "
                f"valid: {sorted(self.VALID_MT_TYPES)}"
            )
        if mt_type in ("103", "202", "202COV"):
            if not payload.get("ordering_customer") and mt_type == "103":
                return False, "MT103 requires ordering_customer (field 50)"
            if not payload.get("beneficiary_bic"):
                return False, "beneficiary_bic required (field 57A or 58A)"
            if not payload.get("amount"):
                return False, "amount required for credit transfer MT"
        return True, ""

    def format_message(self, req: ChannelRequest) -> Dict[str, Any]:
        mt_type = req.payload.get("mt_type", "103")
        sender = "ECOCKENA"  # Ecobank Kenya BIC (illustrative)
        receiver = req.payload.get("beneficiary_bic", "BBBBKENA")
        ref = req.reference or f"REF-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        value_date = now.strftime("%y%m%d")

        # SWIFT block 1+2+3+4+5
        block_1 = f"{{1:F01{sender}AXXX0000000000}}"
        block_2 = f"{{2:I{mt_type}{receiver}XXXXN}}"
        block_3 = f"{{3:{{108:{ref}}}}}"

        if mt_type == "103":
            block_4 = (
                f"{{4:\n"
                f":20:{ref}\n"
                f":23B:CRED\n"
                f":32A:{value_date}{req.currency}{req.amount or 0:.2f}\n"
                f":50K:/{req.debit_account or ''}\n"
                f"{req.payload.get('ordering_customer','ORDERING CUSTOMER')}\n"
                f":59:/{req.credit_account or ''}\n"
                f"{req.payload.get('beneficiary_name','BENEFICIARY NAME')}\n"
                f":71A:OUR\n"
                f"-}}"
            )
        elif mt_type in ("202", "202COV"):
            block_4 = (
                f"{{4:\n"
                f":20:{ref}\n"
                f":21:{req.payload.get('related_reference', ref)}\n"
                f":32A:{value_date}{req.currency}{req.amount or 0:.2f}\n"
                f":58A:{req.payload.get('beneficiary_bic')}\n"
                f"-}}"
            )
        else:
            block_4 = f"{{4:\n:20:{ref}\n-}}"

        block_5 = "{5:{CHK:000000000000}}"
        envelope = block_1 + block_2 + block_3 + block_4 + block_5
        return {
            "MTType": mt_type,
            "Sender": sender,
            "Receiver": receiver,
            "Reference": ref,
            "ValueDate": value_date,
            "RawMT": envelope,
        }


__all__ = ["SwiftSimulator"]
