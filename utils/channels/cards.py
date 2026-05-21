"""utils/channels/cards.py — Card transaction (Visa/Mastercard) simulator.

Card-not-present (e-commerce, recurring) AND card-present (POS) merchant
authorization. ISO 8583 0100 over Visa/MC switch networks.

Distinct from utils/channels/atm.py which is ATM cash withdrawal (0200).
This one is merchant authorization (0100).

Realistic profile:
  - Authorization round-trip p50 ~400ms, p99 ~2s (extremely fast)
  - Failure modes most-frequent: insufficient funds, do-not-honor,
    fraud declined, expired card, AVS mismatch, CVV invalid
  - 3DS step-up required for high-value CNP (returned as a soft-decline
    requiring further customer authentication)
  - Volume: high (largest transaction volume of all banking channels)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
import uuid

from utils.channels.base import (
    BaseChannelSimulator, ChannelStatus, ChannelRequest,
)


class CardsSimulator(BaseChannelSimulator):
    """Simulator for card authorization (Visa/Mastercard 0100)."""

    channel_name = "cards"

    # Cards are the fastest of all channels — merchant SLAs are tight
    latency_p50_ms = 400.0
    latency_p99_ms = 2_000.0

    failure_modes = {
        ChannelStatus.FAILED_INSUFFICIENT_FUNDS: 0.028,
        ChannelStatus.FAILED_CARD_BLOCKED: 0.012,         # blocked / fraud
        ChannelStatus.FAILED_LIMIT_EXCEEDED: 0.008,
        ChannelStatus.FAILED_TIMEOUT: 0.003,
        ChannelStatus.FAILED_HOST_UNAVAILABLE: 0.002,
        ChannelStatus.FAILED_INVALID_PAYLOAD: 0.005,
    }

    # 3DS step-up threshold (RBI-style; Kenya CBK adopting similar)
    THREEDS_STEPUP_KES = 5_000.0    # CNP > this needs 3DS challenge
    CARD_SCHEMES = {"VISA", "MASTERCARD", "VERVE", "DISCOVER", "AMEX"}

    VALID_OPERATIONS = {
        "AUTH",          # Authorization only (no capture)
        "AUTH_CAPTURE",  # Authorization + capture (purchase)
        "REFUND",        # Refund a prior capture
        "VOID",          # Void an unsettled auth
        "RECURRING",     # Recurring/initial CIT
    }

    def validate_payload(self, payload: Dict[str, Any]) -> tuple:
        op = str(payload.get("operation") or "").upper()
        if op not in self.VALID_OPERATIONS:
            return False, (
                f"operation must be one of {sorted(self.VALID_OPERATIONS)}"
            )
        pan = str(payload.get("pan") or "")
        if not pan or not pan.isdigit() or not (13 <= len(pan) <= 19):
            return False, "pan must be 13-19 digit string (PCI format)"
        # BIN-range sanity for known schemes
        bin6 = pan[:6]
        scheme = self._infer_scheme(pan)
        if scheme not in self.CARD_SCHEMES:
            return False, (
                f"BIN {bin6} not in supported card schemes; expected one of "
                f"VISA/MASTERCARD/VERVE/DISCOVER/AMEX"
            )
        amount = payload.get("amount") or 0
        if op != "VOID" and amount <= 0:
            return False, "amount required (positive) for AUTH/CAPTURE/REFUND"
        # Card-not-present requires CVV
        cnp = bool(payload.get("card_not_present", False))
        if cnp and not payload.get("cvv"):
            return False, "cvv required for card-not-present (CNP)"
        cvv = str(payload.get("cvv") or "")
        if cvv and not (cvv.isdigit() and len(cvv) in (3, 4)):
            return False, "cvv must be 3-4 digit numeric"
        # Expiry format
        expiry = str(payload.get("expiry") or "")
        if expiry and not (len(expiry) == 5 and expiry[2] == "/"
                            and expiry[:2].isdigit() and expiry[3:].isdigit()):
            return False, "expiry must be MM/YY format"
        return True, ""

    def submit(self, req):
        """Override to add 3DS step-up handling before standard pipeline.

        For card-not-present transactions above THREEDS_STEPUP_KES, we
        return a soft-decline (FAILED_RATE_LIMITED is the closest enum;
        in real cards this is a 3DS challenge required response). The
        merchant would then redirect the customer to a 3DS challenge
        and retry with the resulting CAVV/ECI.
        """
        payload = req.payload or {}
        cnp = bool(payload.get("card_not_present", False))
        amount = req.amount or payload.get("amount") or 0
        threeds_completed = bool(payload.get("threeds_completed", False))

        if cnp and amount and amount >= self.THREEDS_STEPUP_KES \
                and not threeds_completed:
            # Force a 3DS-required outcome
            import time
            start = time.time()
            corr_id = self._new_correlation_id(req)
            parent_event_id = self._emit_start(req, corr_id)
            response = self._fail(
                req, corr_id, parent_event_id, start,
                ChannelStatus.FAILED_RATE_LIMITED,   # closest enum
                "3DS_REQUIRED",
                f"3DS challenge required for CNP >= KES "
                f"{self.THREEDS_STEPUP_KES:,.0f}",
            )
            return response

        # Otherwise run the normal pipeline
        return super().submit(req)

    def format_message(self, req: ChannelRequest) -> Dict[str, Any]:
        pan = str(req.payload.get("pan", ""))
        masked = f"{pan[:6]}{'*' * max(len(pan) - 10, 4)}{pan[-4:]}"
        op = req.payload.get("operation", "AUTH_CAPTURE")
        scheme = self._infer_scheme(pan)
        cnp = bool(req.payload.get("card_not_present", False))
        stan = req.payload.get("stan") or uuid.uuid4().hex[:6].upper()
        rrn = uuid.uuid4().hex[:12].upper()  # Retrieval Reference Number
        now = datetime.now(timezone.utc)
        return {
            "MessageType": "0100",          # auth request (vs ATM 0200)
            "ProcessingCode": {
                "AUTH":         "003000",   # PRE-AUTH (no capture)
                "AUTH_CAPTURE": "000000",   # PURCHASE
                "REFUND":       "200000",
                "VOID":         "020000",
                "RECURRING":    "001000",
            }.get(op, "000000"),
            "STAN": stan,
            "RRN": rrn,
            "PrimaryAccountNumber": masked,
            "CardScheme": scheme,
            "POSEntryMode": "012" if cnp else "021",  # CNP keyed / CP swipe
            "Amount": int((req.amount or 0) * 100),  # cents
            "TransmissionDateTime": now.strftime("%m%d%H%M%S"),
            "MerchantId": req.payload.get("merchant_id", "ECOM000001"),
            "TerminalId": req.payload.get("terminal_id",
                                            "ECOM00000001" if cnp else "ECOPOS01"),
            "AcquirerInstitutionId": "ECOCKENA",
            "Currency": "404" if req.currency == "KES" else "840",
            "CardNotPresent": cnp,
            "ThreedsCompleted": bool(req.payload.get("threeds_completed", False)),
        }

    def _infer_scheme(self, pan: str) -> str:
        """Identify card scheme from BIN range."""
        if not pan:
            return "UNKNOWN"
        if pan.startswith("4"):
            return "VISA"
        bin2 = pan[:2]
        bin4 = pan[:4]
        # Mastercard: 51-55 or 2221-2720
        if 51 <= int(bin2 or 0) <= 55:
            return "MASTERCARD"
        if pan[:4].isdigit() and 2221 <= int(bin4) <= 2720:
            return "MASTERCARD"
        # Amex: 34 or 37
        if bin2 in ("34", "37"):
            return "AMEX"
        # Discover: 6011, 65, 644-649
        if bin4 == "6011" or bin2 == "65":
            return "DISCOVER"
        # Verve (Nigerian/African scheme): 5060/5061/5078 + others
        if pan.startswith(("5060", "5061", "5078", "5079", "6500")):
            return "VERVE"
        return "UNKNOWN"


__all__ = ["CardsSimulator"]
