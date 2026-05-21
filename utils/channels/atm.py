"""utils/channels/atm.py — ATM ISO 8583 simulator.

Card-present cash withdrawal / balance inquiry / mini-statement.
Realistic ATM round-trip: ~700ms p50, up to 3s p99.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
import uuid

from utils.channels.base import (
    BaseChannelSimulator, ChannelStatus, ChannelRequest,
)


class ATMSimulator(BaseChannelSimulator):
    """Simulator for ATM ISO 8583 traffic."""

    channel_name = "atm"

    # ATM round-trip target: 700ms p50 (real-world ~500-1500ms)
    latency_p50_ms = 700.0
    latency_p99_ms = 3_000.0

    failure_modes = {
        ChannelStatus.FAILED_INSUFFICIENT_FUNDS: 0.025,
        ChannelStatus.FAILED_CARD_BLOCKED: 0.008,
        ChannelStatus.FAILED_PIN_EXCEEDED: 0.004,
        ChannelStatus.FAILED_LIMIT_EXCEEDED: 0.006,
        ChannelStatus.FAILED_TIMEOUT: 0.003,
        ChannelStatus.FAILED_DISPENSER: 0.002,
        ChannelStatus.FAILED_HOST_UNAVAILABLE: 0.002,
    }

    VALID_OPERATIONS = {"WITHDRAWAL", "BALANCE_INQUIRY",
                         "MINI_STATEMENT", "PIN_CHANGE", "DEPOSIT"}

    def validate_payload(self, payload: Dict[str, Any]) -> tuple:
        op = str(payload.get("operation") or "").upper()
        if op not in self.VALID_OPERATIONS:
            return False, f"operation must be one of {sorted(self.VALID_OPERATIONS)}"
        pan = str(payload.get("pan") or "")
        if not pan or not pan.isdigit() or not (12 <= len(pan) <= 19):
            return False, "pan must be 12-19 digit string"
        if op == "WITHDRAWAL":
            amount = payload.get("amount") or 0
            if amount <= 0:
                return False, "withdrawal requires positive amount"
            if amount % 100 != 0:  # KES denominations: multiples of 100
                return False, "ATM amount must be multiple of KES 100"
        return True, ""

    def format_message(self, req: ChannelRequest) -> Dict[str, Any]:
        """Build minimal ISO 8583 0200 message representation."""
        op = req.payload.get("operation", "WITHDRAWAL")
        pan = str(req.payload.get("pan", ""))
        masked = f"{pan[:6]}{'*' * max(len(pan) - 10, 4)}{pan[-4:]}"
        stan = req.payload.get("stan") or uuid.uuid4().hex[:6].upper()
        now = datetime.now(timezone.utc)
        return {
            "MessageType": "0200",
            "STAN": stan,
            "PrimaryAccountNumber": masked,
            "ProcessingCode": {
                "WITHDRAWAL": "010000",
                "BALANCE_INQUIRY": "300000",
                "MINI_STATEMENT": "380000",
                "PIN_CHANGE": "920000",
                "DEPOSIT": "210000",
            }.get(op, "010000"),
            "Amount": int((req.amount or 0) * 100),  # ISO 8583 amount in cents
            "TransmissionDateTime": now.strftime("%m%d%H%M%S"),
            "TerminalId": req.payload.get("terminal_id", "ECONA0001"),
            "AcquirerInstitutionId": "0000ECONA",
            "Currency": "404" if req.currency == "KES" else "840",
        }


__all__ = ["ATMSimulator"]
