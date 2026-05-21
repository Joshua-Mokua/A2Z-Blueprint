"""utils/channels/ussd.py — USSD session simulator.

Feature-phone USSD codes (*334#). Session-oriented; each menu hop is
a separate USSD request. Payload size cap 182 chars per message.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from utils.channels.base import (
    BaseChannelSimulator, ChannelStatus, ChannelRequest,
)


class USSDSimulator(BaseChannelSimulator):
    """Simulator for USSD session traffic."""

    channel_name = "ussd"

    # Per-hop USSD latency: 1-5s
    latency_p50_ms = 1_500.0
    latency_p99_ms = 5_000.0

    failure_modes = {
        ChannelStatus.FAILED_SESSION_TIMEOUT: 0.020,
        ChannelStatus.FAILED_NETWORK: 0.015,
        ChannelStatus.FAILED_INVALID_PAYLOAD: 0.005,
        ChannelStatus.FAILED_HOST_UNAVAILABLE: 0.003,
    }

    MAX_PAYLOAD_CHARS = 182

    def validate_payload(self, payload: Dict[str, Any]) -> tuple:
        ussd_code = str(payload.get("ussd_code") or "")
        if not ussd_code or not (ussd_code.startswith("*") and ussd_code.endswith("#")):
            return False, "ussd_code must start with * and end with #"
        msisdn = str(payload.get("msisdn") or "")
        if not msisdn or not msisdn.isdigit() or len(msisdn) < 9:
            return False, "msisdn (mobile number) required, digits only"
        text = str(payload.get("text") or "")
        if len(text) > self.MAX_PAYLOAD_CHARS:
            return False, (
                f"USSD payload {len(text)} exceeds {self.MAX_PAYLOAD_CHARS}-char limit"
            )
        return True, ""

    def format_message(self, req: ChannelRequest) -> Dict[str, Any]:
        sess = req.payload.get("session_id") or f"USSD-{req.reference or ''}"
        return {
            "SessionId": sess,
            "ServiceCode": req.payload.get("ussd_code"),
            "Msisdn": req.payload.get("msisdn"),
            "Text": req.payload.get("text", ""),
            "NetworkCode": req.payload.get("network_code", "63902"),  # Safaricom
            "Timestamp": datetime.now(timezone.utc).isoformat(),
        }


__all__ = ["USSDSimulator"]
