"""utils/channels/mpesa.py — Safaricom M-Pesa Daraja simulator.

Covers STK Push (CustomerPayBillOnline), B2C (BusinessPayment), C2B
(URL registration + callback). Asynchronous: STK Push returns a
checkout request id; the actual money movement is confirmed via
callback. We model the synchronous accept step here.

Realistic Kenyan latency: STK push initiate ~3-7s, full flow incl
customer PIN entry can take 30-60s. We measure the initiate latency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
import uuid

from utils.channels.base import (
    BaseChannelSimulator, ChannelStatus, ChannelRequest,
)


class MPesaSimulator(BaseChannelSimulator):
    """Simulator for Safaricom M-Pesa Daraja API."""

    channel_name = "mpesa"

    # STK push initiate latency: 3-7s typical
    latency_p50_ms = 4_000.0
    latency_p99_ms = 30_000.0

    failure_modes = {
        ChannelStatus.FAILED_INSUFFICIENT_FUNDS: 0.018,
        ChannelStatus.FAILED_KYC_LIMIT: 0.010,
        ChannelStatus.FAILED_CALLBACK_TIMEOUT: 0.008,
        ChannelStatus.FAILED_TIMEOUT: 0.005,
        ChannelStatus.FAILED_RATE_LIMITED: 0.003,
        ChannelStatus.FAILED_INVALID_PAYLOAD: 0.005,
    }

    VALID_TRANSACTION_TYPES = {
        "CustomerPayBillOnline",
        "CustomerBuyGoodsOnline",
        "BusinessPayment",
        "BusinessBuyGoods",
        "SalaryPayment",
        "PromotionPayment",
        "AccountBalance",
    }

    # M-Pesa daily transaction limits (Tier 1+2)
    DAILY_LIMIT = 300_000.0       # KES
    SINGLE_TXN_LIMIT = 150_000.0  # KES

    def validate_payload(self, payload: Dict[str, Any]) -> tuple:
        txn_type = payload.get("transaction_type")
        if txn_type not in self.VALID_TRANSACTION_TYPES:
            return False, (
                f"transaction_type must be one of "
                f"{sorted(self.VALID_TRANSACTION_TYPES)}"
            )
        msisdn = str(payload.get("msisdn") or "")
        if not msisdn:
            return False, "msisdn required"
        if not (msisdn.startswith("2547") or msisdn.startswith("2541")):
            return False, "msisdn must be Kenyan format (254 7xx / 254 1xx)"
        if len(msisdn) != 12:
            return False, "msisdn must be 12 digits incl 254 country code"
        amount = payload.get("amount") or 0
        if amount <= 0:
            return False, "amount must be positive"
        if amount > self.SINGLE_TXN_LIMIT:
            return False, (
                f"amount exceeds M-Pesa single-transaction limit "
                f"KES {self.SINGLE_TXN_LIMIT:,.0f}"
            )
        if txn_type in ("CustomerPayBillOnline", "CustomerBuyGoodsOnline"):
            if not payload.get("paybill") and not payload.get("till_number"):
                return False, "paybill or till_number required for customer-pay"
        return True, ""

    def format_message(self, req: ChannelRequest) -> Dict[str, Any]:
        txn_type = req.payload.get("transaction_type")
        checkout_id = f"ws_CO_{datetime.now(timezone.utc).strftime('%d%m%Y%H%M%S')}{uuid.uuid4().hex[:6]}"
        merchant_id = req.payload.get("paybill") or req.payload.get("till_number") or "174379"
        return {
            "MerchantRequestID": uuid.uuid4().hex,
            "CheckoutRequestID": checkout_id,
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success. Request accepted for processing",
            "TransactionType": txn_type,
            "Amount": req.amount,
            "PartyA": req.payload.get("msisdn"),
            "PartyB": merchant_id,
            "PhoneNumber": req.payload.get("msisdn"),
            "BusinessShortCode": merchant_id,
            "AccountReference": req.payload.get("account_reference",
                                                 req.reference or "Ecobank"),
            "TransactionDesc": req.payload.get("description", "Payment"),
            "Timestamp": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        }


__all__ = ["MPesaSimulator"]
