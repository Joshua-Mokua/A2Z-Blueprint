"""utils/channels/base.py — Shared types for channel simulators.

Every simulator returns a ChannelResponse with the same envelope so
callers can handle them uniformly. Each simulator emits start +
success/failure events into event_bus with a shared correlation_id.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class ChannelStatus(str, Enum):
    """Status of a channel submission."""
    SUCCESS = "success"
    FAILED_TIMEOUT = "failed_timeout"
    FAILED_INSUFFICIENT_FUNDS = "failed_insufficient_funds"
    FAILED_LIMIT_EXCEEDED = "failed_limit_exceeded"
    FAILED_INVALID_PAYLOAD = "failed_invalid_payload"
    FAILED_BENEFICIARY_REJECT = "failed_beneficiary_reject"
    FAILED_SANCTIONS_HIT = "failed_sanctions_hit"
    FAILED_RATE_LIMITED = "failed_rate_limited"
    FAILED_HOST_UNAVAILABLE = "failed_host_unavailable"
    FAILED_CUTOFF = "failed_cutoff"
    FAILED_CARD_BLOCKED = "failed_card_blocked"
    FAILED_PIN_EXCEEDED = "failed_pin_exceeded"
    FAILED_DISPENSER = "failed_dispenser_jam"
    FAILED_SESSION_TIMEOUT = "failed_session_timeout"
    FAILED_NETWORK = "failed_network_drop"
    FAILED_KYC_LIMIT = "failed_kyc_limit"
    FAILED_CALLBACK_TIMEOUT = "failed_callback_timeout"
    FAILED_OTHER = "failed_other"


@dataclass
class ChannelRequest:
    """Generic channel request envelope."""
    channel: str
    payload: Dict[str, Any]
    amount: Optional[float] = None
    currency: str = "KES"
    debit_account: Optional[str] = None
    credit_account: Optional[str] = None
    reference: Optional[str] = None
    actor: str = "system"
    correlation_id_override: Optional[str] = None  # v10.479: scenario can pin a shared correlation_id


@dataclass
class ChannelResponse:
    """Generic channel response envelope."""
    channel: str
    status: ChannelStatus
    latency_ms: float
    timestamp: str
    correlation_id: str
    message_id: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if hasattr(self.status, "value") else str(self.status)
        return d


class BaseChannelSimulator:
    """Base class for all channel simulators.

    Subclasses override:
      - channel_name (str)
      - latency_p50_ms, latency_p99_ms (float)
      - failure_modes: dict mapping ChannelStatus -> probability (0.0-1.0)
      - validate_payload(payload) -> tuple[bool, str]  # returns (ok, reason)
      - format_message(req) -> dict  # the channel-specific envelope

    Subclasses should call super().submit(req) to inherit:
      - Correlation id generation
      - Event bus emission (integration.<channel>.call / .success / .failure)
      - Latency simulation
      - Failure mode injection
      - Validation
    """

    channel_name: str = "base"
    latency_p50_ms: float = 100.0
    latency_p99_ms: float = 1000.0
    failure_modes: Dict[ChannelStatus, float] = {}

    def __init__(self, *, seed: Optional[int] = None,
                 simulate_real_latency: bool = False):
        """Args:
            seed: If given, makes all random outcomes deterministic.
            simulate_real_latency: If True, time.sleep() the latency
                (slow). If False (default), latency is computed and
                reported but not slept.
        """
        self._rng = random.Random(seed)
        self._simulate_real_latency = simulate_real_latency

    # ── Hooks for subclasses ─────────────────────────────────────
    def validate_payload(self, payload: Dict[str, Any]) -> tuple:
        return True, ""

    def format_message(self, req: ChannelRequest) -> Dict[str, Any]:
        return {"payload": req.payload}

    # ── Core submit pipeline ─────────────────────────────────────
    def submit(self, req: ChannelRequest) -> ChannelResponse:
        start = time.time()
        # v10.479: scenarios pin a shared correlation_id so all channel
        # calls within a scenario belong to one traceable group
        corr_id = req.correlation_id_override or self._new_correlation_id(req)

        # Emit start event
        parent_event_id = self._emit_start(req, corr_id)

        # Merge top-level req.amount into payload for validation convenience
        # (callers may pass amount as kwarg OR inside payload — accept either)
        _validation_payload = dict(req.payload or {})
        if req.amount is not None and "amount" not in _validation_payload:
            _validation_payload["amount"] = req.amount
        if req.debit_account and "debit_account" not in _validation_payload:
            _validation_payload["debit_account"] = req.debit_account
        if req.credit_account and "credit_account" not in _validation_payload:
            _validation_payload["credit_account"] = req.credit_account

        # Validate payload
        ok, reason = self.validate_payload(_validation_payload)
        if not ok:
            response = self._fail(req, corr_id, parent_event_id, start,
                                   ChannelStatus.FAILED_INVALID_PAYLOAD,
                                   "VALIDATION", reason)
            return response

        # ── v10.482 O5 chaos hook ─────────────────────────────────
        # Check active chaos events for this channel and either fail
        # the request outright (channel_outage / scheme_degraded /
        # elevated_failure) or scale latency (latency_spike). Each kind
        # composes with existing failure_modes probabilistically.
        try:
            from utils.chaos.injector import get_chaos_injector
            injector = get_chaos_injector()
            if injector.is_channel_outage(self.channel_name):
                response = self._fail(
                    req, corr_id, parent_event_id, start,
                    ChannelStatus.FAILED_HOST_UNAVAILABLE,
                    "CHAOS_OUTAGE",
                    f"chaos: channel {self.channel_name} in outage window",
                )
                return response
            chaos_failure_rate = injector.elevated_failure_rate(
                self.channel_name)
            chaos_latency_mult = injector.latency_multiplier(
                self.channel_name)
        except Exception:
            chaos_failure_rate = 0.0
            chaos_latency_mult = 1.0

        # Simulate latency (scaled by chaos latency multipliers)
        latency_ms = self._sample_latency() * chaos_latency_mult
        if self._simulate_real_latency:
            time.sleep(latency_ms / 1000.0)

        # Chaos elevated failure rolls before normal failure sampling
        if chaos_failure_rate > 0 and self._rng.random() < chaos_failure_rate:
            response = self._fail(
                req, corr_id, parent_event_id, start,
                ChannelStatus.FAILED_HOST_UNAVAILABLE,
                "CHAOS_FAILURE",
                f"chaos: elevated failure rate {chaos_failure_rate:.0%}",
                latency_ms=latency_ms,
            )
            return response

        # Inject failures (regular failure_modes)
        status = self._sample_status()
        if status != ChannelStatus.SUCCESS:
            response = self._fail(req, corr_id, parent_event_id, start,
                                   status,
                                   self._error_code_for(status),
                                   self._error_message_for(status),
                                   latency_ms=latency_ms)
            return response

        # Success path
        envelope = self.format_message(req)
        message_id = hashlib.sha256(
            f"{self.channel_name}|{corr_id}|{req.actor}".encode("utf-8")
        ).hexdigest()[:16]
        response = ChannelResponse(
            channel=self.channel_name,
            status=ChannelStatus.SUCCESS,
            success=True,
            latency_ms=latency_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
            correlation_id=corr_id,
            message_id=message_id,
            raw_response=envelope,
        )
        self._emit_success(req, response, parent_event_id)
        return response

    # ── Helpers ──────────────────────────────────────────────────
    def _new_correlation_id(self, req: ChannelRequest) -> str:
        seed = f"{self.channel_name}|{req.reference or ''}|{time.time()}|{self._rng.random()}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

    def _sample_latency(self) -> float:
        # Lognormal-ish: most below p50, long tail toward p99
        u = self._rng.random()
        if u < 0.5:
            return self.latency_p50_ms * (0.6 + u * 0.8)
        elif u < 0.95:
            return self.latency_p50_ms + (
                (self.latency_p99_ms - self.latency_p50_ms) *
                ((u - 0.5) / 0.45) ** 1.5
            )
        else:
            return self.latency_p99_ms * (1.0 + (u - 0.95) * 4)

    def _sample_status(self) -> ChannelStatus:
        u = self._rng.random()
        cumulative = 0.0
        for status, prob in self.failure_modes.items():
            cumulative += prob
            if u < cumulative:
                return status
        return ChannelStatus.SUCCESS

    def _error_code_for(self, status: ChannelStatus) -> str:
        mapping = {
            ChannelStatus.FAILED_TIMEOUT: "TIMEOUT",
            ChannelStatus.FAILED_INSUFFICIENT_FUNDS: "INSF_FUNDS",
            ChannelStatus.FAILED_LIMIT_EXCEEDED: "LIMIT_EXCD",
            ChannelStatus.FAILED_BENEFICIARY_REJECT: "BEN_REJECT",
            ChannelStatus.FAILED_SANCTIONS_HIT: "SANCTIONS",
            ChannelStatus.FAILED_RATE_LIMITED: "RATE_LIMIT",
            ChannelStatus.FAILED_HOST_UNAVAILABLE: "HOST_DOWN",
            ChannelStatus.FAILED_CUTOFF: "CUTOFF",
            ChannelStatus.FAILED_CARD_BLOCKED: "CARD_BLOCK",
            ChannelStatus.FAILED_PIN_EXCEEDED: "PIN_LOCK",
            ChannelStatus.FAILED_DISPENSER: "DISP_JAM",
            ChannelStatus.FAILED_SESSION_TIMEOUT: "SESS_TMO",
            ChannelStatus.FAILED_NETWORK: "NET_DROP",
            ChannelStatus.FAILED_KYC_LIMIT: "KYC_LIMIT",
            ChannelStatus.FAILED_CALLBACK_TIMEOUT: "CB_TIMEOUT",
        }
        return mapping.get(status, "OTHER")

    def _error_message_for(self, status: ChannelStatus) -> str:
        mapping = {
            ChannelStatus.FAILED_TIMEOUT: "Upstream timeout",
            ChannelStatus.FAILED_INSUFFICIENT_FUNDS: "Insufficient funds",
            ChannelStatus.FAILED_LIMIT_EXCEEDED: "Limit exceeded",
            ChannelStatus.FAILED_BENEFICIARY_REJECT: "Beneficiary bank rejected",
            ChannelStatus.FAILED_SANCTIONS_HIT: "Sanctions screening hit",
            ChannelStatus.FAILED_RATE_LIMITED: "Rate limit exceeded",
            ChannelStatus.FAILED_HOST_UNAVAILABLE: "Host unavailable",
            ChannelStatus.FAILED_CUTOFF: "Past channel cut-off",
            ChannelStatus.FAILED_CARD_BLOCKED: "Card blocked",
            ChannelStatus.FAILED_PIN_EXCEEDED: "PIN tries exceeded",
            ChannelStatus.FAILED_DISPENSER: "ATM dispenser jam",
            ChannelStatus.FAILED_SESSION_TIMEOUT: "USSD session timeout",
            ChannelStatus.FAILED_NETWORK: "Mobile network drop",
            ChannelStatus.FAILED_KYC_LIMIT: "KYC tier limit reached",
            ChannelStatus.FAILED_CALLBACK_TIMEOUT: "Callback never received",
        }
        return mapping.get(status, "Unknown failure")

    def _fail(self, req, corr_id, parent_event_id, start_t,
              status, code, msg, latency_ms: Optional[float] = None
              ) -> ChannelResponse:
        if latency_ms is None:
            latency_ms = (time.time() - start_t) * 1000.0
        response = ChannelResponse(
            channel=self.channel_name, status=status, success=False,
            latency_ms=latency_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
            correlation_id=corr_id, error_code=code, error_message=msg,
        )
        self._emit_failure(req, response, parent_event_id)
        return response

    def _emit_start(self, req, corr_id) -> Optional[str]:
        try:
            from utils.event_bus import get_event_bus
            return get_event_bus().emit(
                event_type=f"integration.{self.channel_name}.call",
                actor=req.actor or "system",
                entity_id=req.reference or "",
                module=f"channel.{self.channel_name}",
                payload={
                    "amount": req.amount, "currency": req.currency,
                    "debit": req.debit_account, "credit": req.credit_account,
                },
                correlation_id=corr_id,
                severity="info",
            )
        except Exception:
            return None

    def _emit_success(self, req, response, parent_event_id) -> None:
        try:
            from utils.event_bus import get_event_bus
            get_event_bus().emit(
                event_type=f"integration.{self.channel_name}.success",
                actor=req.actor or "system",
                entity_id=req.reference or response.message_id or "",
                module=f"channel.{self.channel_name}",
                payload={
                    "amount": req.amount, "currency": req.currency,
                    "latency_ms": response.latency_ms,
                    "message_id": response.message_id,
                },
                correlation_id=response.correlation_id,
                parent_event_id=parent_event_id,
                severity="info",
            )
        except Exception:
            pass

    def _emit_failure(self, req, response, parent_event_id) -> None:
        try:
            from utils.event_bus import get_event_bus
            sev = "error" if response.status == ChannelStatus.FAILED_SANCTIONS_HIT \
                else "warning"
            get_event_bus().emit(
                event_type=f"integration.{self.channel_name}.failure",
                actor=req.actor or "system",
                entity_id=req.reference or "",
                module=f"channel.{self.channel_name}",
                payload={
                    "amount": req.amount, "currency": req.currency,
                    "latency_ms": response.latency_ms,
                    "error_code": response.error_code,
                    "error_message": response.error_message,
                    "status": response.status.value,
                },
                correlation_id=response.correlation_id,
                parent_event_id=parent_event_id,
                severity=sev,
            )
        except Exception:
            pass


__all__ = ["ChannelStatus", "ChannelRequest", "ChannelResponse",
           "BaseChannelSimulator"]
