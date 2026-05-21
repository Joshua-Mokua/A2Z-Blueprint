"""utils/channels/kic.py — Kenya Interbank Clearing (KEPSS-EFT/cheque).

Kenya's automated clearing house — operated by KEPSS, handles:
  - EFT (low-value bulk credit transfers below RTGS threshold)
  - Cheque truncation (image-based clearing)
  - Direct debits (for utility-style recurring collections)

Use this for amounts < KES 1M (above goes to RTGS). T+0 same-day for
EFTs submitted before noon, T+1 for after-noon batches and cheques.
We simulate the submission/accept step; final clearing is asynchronous.

Realistic profile (Ecobank Kenya):
  - Submission latency p50 ~1.5min, p99 ~10min (batch-oriented)
  - Failure modes most-frequent: account mismatch, account closed,
    KYC tier limit, batch rejected by clearing house, beneficiary
    bank not in scheme
  - Volume: thousands per day per Tier-1 bank
"""

from __future__ import annotations

from datetime import datetime, time as dt_time, timezone, timedelta
from typing import Any, Dict
import uuid

from utils.simulation_clock import sim_now, NAIROBI_TZ

from utils.channels.base import (
    BaseChannelSimulator, ChannelStatus, ChannelRequest,
)


class KICSimulator(BaseChannelSimulator):
    """Simulator for Kenya Interbank Clearing (KEPSS-EFT + cheque)."""

    channel_name = "kic"

    # KIC submission/accept latency
    latency_p50_ms = 90_000.0    # 1.5 minutes (batch acceptance)
    latency_p99_ms = 600_000.0   # 10 minutes

    failure_modes = {
        ChannelStatus.FAILED_BENEFICIARY_REJECT: 0.020,  # account closed / mismatch
        ChannelStatus.FAILED_INVALID_PAYLOAD: 0.008,
        ChannelStatus.FAILED_KYC_LIMIT: 0.006,
        ChannelStatus.FAILED_CUTOFF: 0.005,             # past batch cutoff
        ChannelStatus.FAILED_HOST_UNAVAILABLE: 0.004,
        ChannelStatus.FAILED_TIMEOUT: 0.003,
        ChannelStatus.FAILED_SANCTIONS_HIT: 0.002,
    }

    # KIC EFT upper bound — above this use RTGS
    MAX_AMOUNT = 1_000_000.0  # KES (matches RTGS minimum)

    # Cutoffs: morning batch 11:30am EAT, afternoon batch 3:30pm EAT
    MORNING_CUTOFF = dt_time(11, 30)
    AFTERNOON_CUTOFF = dt_time(15, 30)

    VALID_TRANSACTION_TYPES = {
        "EFT_CREDIT",       # Bulk EFT (salary, supplier)
        "EFT_DEBIT",        # Direct debit (utility-style)
        "CHEQUE_INWARD",    # Inward cheque clearing
        "CHEQUE_OUTWARD",   # Outward cheque collection
    }

    def validate_payload(self, payload: Dict[str, Any]) -> tuple:
        txn_type = str(payload.get("transaction_type") or "").upper()
        if txn_type not in self.VALID_TRANSACTION_TYPES:
            return False, (
                f"transaction_type must be one of "
                f"{sorted(self.VALID_TRANSACTION_TYPES)}"
            )
        amount = payload.get("amount") or 0
        if not amount or amount <= 0:
            return False, "positive amount required"
        if amount > self.MAX_AMOUNT:
            return False, (
                f"KIC EFT maximum is KES {self.MAX_AMOUNT:,.0f}; "
                f"use RTGS for high-value"
            )
        if not payload.get("debit_account") and txn_type != "CHEQUE_INWARD":
            return False, "debit_account required (sending bank)"
        if not payload.get("credit_account"):
            return False, "credit_account required (receiving)"
        if not payload.get("beneficiary_bank_code"):
            return False, (
                "beneficiary_bank_code required (3-digit CBK bank code, "
                "e.g. '011' for Cooperative Bank)"
            )
        bcode = str(payload.get("beneficiary_bank_code"))
        if not (bcode.isdigit() and len(bcode) == 3):
            return False, "beneficiary_bank_code must be 3-digit CBK code"
        if txn_type.startswith("CHEQUE"):
            if not payload.get("cheque_number"):
                return False, "cheque_number required for CHEQUE_* transactions"
        return True, ""

    def format_message(self, req: ChannelRequest) -> Dict[str, Any]:
        """Build a KIC batch-record envelope (one record).

        Uses ``sim_now()`` for the timestamp so that when the sim clock
        is active (Phase O4-A), batch windows reflect simulation time
        rather than wall time. With the sim clock inactive, sim_now()
        returns wall-clock UTC — behaviour is unchanged.
        """
        txn_type = req.payload.get("transaction_type", "EFT_CREDIT")
        now = sim_now()
        nairobi = now.astimezone(NAIROBI_TZ)
        batch_id = f"KIC-{nairobi.strftime('%Y%m%d')}-{self._batch_window(nairobi)}-{uuid.uuid4().hex[:6].upper()}"
        return {
            "RecordType": txn_type,
            "BatchId": batch_id,
            "BatchWindow": self._batch_window(nairobi),
            "SendingBank": "ECOCKENA",
            "SendingBankCode": "044",  # Ecobank Kenya CBK code (illustrative)
            "ReceivingBankCode": req.payload.get("beneficiary_bank_code"),
            "DebitAccount": req.payload.get("debit_account") or "",
            "CreditAccount": req.payload.get("credit_account"),
            "Amount": req.amount,
            "Currency": "KES",
            "ValueDate": nairobi.date().isoformat(),
            "Reference": req.reference or batch_id,
            "Narrative": req.payload.get("narrative", "")[:35],  # KIC limit
            "ChequeNumber": req.payload.get("cheque_number") or None,
            "ExpectedSettlement": self._expected_settlement(nairobi).isoformat(),
        }

    def _batch_window(self, now: datetime) -> str:
        """Determine which KIC batch window the current time falls into."""
        t = now.time() if isinstance(now, datetime) else now
        if t < self.MORNING_CUTOFF:
            return "MORNING"
        elif t < self.AFTERNOON_CUTOFF:
            return "AFTERNOON"
        else:
            return "NEXT_DAY_MORNING"

    def _expected_settlement(self, now: datetime):
        """T+0 or T+1 depending on submission window."""
        window = self._batch_window(now)
        if window == "MORNING":
            return now.date()  # same-day clearing
        elif window == "AFTERNOON":
            return now.date() + timedelta(days=1)  # next-day
        else:
            return now.date() + timedelta(days=1)  # next-day morning batch


__all__ = ["KICSimulator"]
