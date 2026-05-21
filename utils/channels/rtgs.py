"""utils/channels/rtgs.py — CBK Real-Time Gross Settlement simulator.

KEPSS-style RTGS. ISO 20022 pacs.008/pacs.009 message format. High-
value KES transfers. Cut-off 4pm Nairobi (local). Final and irrevocable.

Realistic profile (Ecobank Kenya volume):
  - Typical p50 latency: 45s  (real RTGS: 30s-5min including beneficiary bank)
  - p99 latency: 5min
  - Failure modes most-frequent: cut-off rejection, beneficiary bank
    unavailable, sanctions screening hit, insufficient liquidity at CBK
  - Volume: hundreds per day per Tier-1 bank
"""

from __future__ import annotations

from datetime import datetime, time as dt_time, timezone, timedelta
from typing import Any, Dict
import uuid

from utils.channels.base import (
    BaseChannelSimulator, ChannelStatus, ChannelRequest,
)


class RTGSSimulator(BaseChannelSimulator):
    """Simulator for Central Bank RTGS (KEPSS-style)."""

    channel_name = "rtgs"

    # Realistic for real-money settlement systems
    latency_p50_ms = 45_000.0   # 45 seconds median
    latency_p99_ms = 300_000.0  # 5 minutes

    failure_modes = {
        ChannelStatus.FAILED_CUTOFF: 0.02,
        ChannelStatus.FAILED_BENEFICIARY_REJECT: 0.015,
        ChannelStatus.FAILED_SANCTIONS_HIT: 0.005,
        ChannelStatus.FAILED_HOST_UNAVAILABLE: 0.005,
        ChannelStatus.FAILED_TIMEOUT: 0.003,
        ChannelStatus.FAILED_INSUFFICIENT_FUNDS: 0.002,
    }

    # CBK RTGS cut-off — typically 4:30pm Nairobi (EAT, UTC+3)
    CUTOFF_HOUR = 16
    CUTOFF_MINUTE = 30

    # Minimum RTGS threshold (typical Kenya): KES 1M (high-value channel)
    MIN_AMOUNT = 1_000_000.0

    def validate_payload(self, payload: Dict[str, Any]) -> tuple:
        amount = payload.get("amount") or 0
        if not amount or amount <= 0:
            return False, "amount required for RTGS"
        if amount < self.MIN_AMOUNT:
            return False, (
                f"RTGS minimum is KES {self.MIN_AMOUNT:,.0f}; use KIC/EFT "
                f"for amounts below threshold"
            )
        if not payload.get("debit_account"):
            return False, "debit_account required"
        if not payload.get("credit_account"):
            return False, "credit_account required"
        if not payload.get("beneficiary_bank_bic"):
            return False, "beneficiary_bank_bic required (8 or 11 char SWIFT BIC)"
        return True, ""

    def format_message(self, req: ChannelRequest) -> Dict[str, Any]:
        """Build ISO 20022 pacs.008 envelope."""
        now = datetime.now(timezone.utc)
        msg_id = f"PACS008-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"
        e2e_id = req.reference or msg_id
        return {
            "MsgType": "pacs.008.001.10",
            "GrpHdr": {
                "MsgId": msg_id,
                "CreDtTm": now.isoformat(),
                "NbOfTxs": 1,
                "CtrlSum": req.amount,
                "InstgAgt": {"FinInstnId": {"BICFI": "ECOCKENA"}},
            },
            "CdtTrfTxInf": {
                "PmtId": {"InstrId": msg_id, "EndToEndId": e2e_id},
                "IntrBkSttlmAmt": {"Ccy": req.currency, "Amount": req.amount},
                "IntrBkSttlmDt": now.date().isoformat(),
                "Dbtr": {"Acct": req.debit_account},
                "DbtrAgt": {"FinInstnId": {"BICFI": "ECOCKENA"}},
                "Cdtr": {"Acct": req.credit_account},
                "CdtrAgt": {
                    "FinInstnId": {
                        "BICFI": req.payload.get("beneficiary_bank_bic"),
                    },
                },
            },
        }

    def is_past_cutoff(self, now: datetime = None) -> bool:
        """Check whether current Nairobi-time is past RTGS cut-off."""
        now = now or datetime.now(timezone.utc)
        nairobi = now.astimezone(timezone(timedelta(hours=3)))
        cutoff = dt_time(self.CUTOFF_HOUR, self.CUTOFF_MINUTE)
        return nairobi.time() >= cutoff


__all__ = ["RTGSSimulator"]
