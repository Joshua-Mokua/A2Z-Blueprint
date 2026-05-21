"""utils/trade_finance_connectivity.py — v10.79: TF connectivity.

ENH-276 — Multi-Bank Connectivity. Cat B — trade_finance arc
10/N.

Diagnostic adapter surface for inbound trade-finance network
messages (we.trade / Marco Polo / Contour / Bolero / SWIFT GPI /
SWIFT FIN). Engine validates message structure, maps foreign
protocol fields to internal schema, classifies routing actions,
and detects protocol-level anomalies. Engine NEVER sends
messages, NEVER connects to networks, NEVER processes payments,
NEVER decides accept/reject — those flows belong to the
operations + payments + RM layers downstream.

Five capabilities:

  1. validate_inbound_message_structure — given a raw inbound
     message dictionary + declared TradeNetwork, validate
     structural conformance (required fields per protocol,
     supported protocol version). 4-tier
     MessageValidationStatus (VALID / MISSING_REQUIRED_FIELDS /
     MALFORMED / UNKNOWN_PROTOCOL).

  2. map_to_internal_schema — given a validated message + caller-
     supplied field-mapping config, project foreign-protocol
     fields onto internal schema with explicit gap surfacing
     (UNMAPPED inbound fields + MISSING required outbound
     fields). Engine never fabricates values.

  3. classify_routing_action — given a mapped message, classify
     internal action (NEW_LC_ISSUANCE / AMENDMENT_NOTIFICATION /
     DRAWDOWN_NOTIFICATION / DOCUMENT_DISPATCH / STATUS_UPDATE /
     PAYMENT_INSTRUCTION / UNKNOWN) using caller-supplied
     message-type → action map.

  4. detect_protocol_anomalies — given a sequence of inbound
     messages, detect duplicate IDs, out-of-order sequences,
     unsupported version mismatches, unknown senders. Surfaces
     anomalies for operator review.

  5. build_connectivity_report — orchestrator: per-network
     message counts + validation outcome distribution + routing-
     action distribution + anomaly counts + top error types.

Per Rule 7, engine NEVER:
  - sends outbound messages or notifications
  - connects to external networks
  - processes payments or settles obligations
  - decides accept/reject on inbound messages (operator
    examines findings + decides per banking workflow)
  - mutates messages or augments fields beyond explicit caller-
    supplied mappings (no implicit fabrication)
  - retains message contents (audit-log responsibility lives
    elsewhere)

Per Rule 1, every output surfaces validation findings + protocol
references + framework_refs + matched fields with sources.

Pure stdlib runtime.
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import (
    Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple)

SPEC_DEVIATION_NOTE = (
    "TradeFinanceConnectivityEngine implements ENH-276 — "
    "diagnostic adapter surface for inbound trade-finance "
    "network messages. Validates structure + maps to internal "
    "schema + classifies routing + detects anomalies + reports. "
    "Engine never sends messages, never connects to networks, "
    "never processes payments, never decides accept/reject "
    "(operator examines findings + decides). Pure stdlib. Per "
    "Rule 1, every output surfaces validation findings + "
    "protocol refs + framework_refs. Per Rule 7, engine "
    "DIAGNOSTIC ONLY — never mutates inputs, never fabricates "
    "values beyond explicit caller-supplied mappings."
)

# Per-protocol required-fields specification. Caller can extend
# via constructor for proprietary protocol variants. These
# defaults reflect publicly-documented field lists of the major
# trade networks as of 2025-2026.
DEFAULT_PROTOCOL_REQUIRED_FIELDS: Mapping[
    str, Tuple[str, ...]] = {
    "WE_TRADE": (
        "message_id", "message_type", "sender_bin",
        "receiver_bin", "lc_reference", "amount", "currency",
        "version"),
    "MARCO_POLO": (
        "message_id", "msg_type", "originator",
        "destination", "trade_id", "amount", "currency",
        "protocol_version"),
    "CONTOUR": (
        "message_id", "type", "from_node", "to_node",
        "lc_id", "amount", "currency"),
    "BOLERO": (
        "message_id", "messageType", "senderId",
        "receiverId", "documentId", "amount", "currency"),
    "SWIFT_GPI": (
        "message_id", "transaction_reference",
        "uetr",        # Unique End-to-End Transaction Reference
        "amount", "currency"),
    "SWIFT_FIN": (
        "message_id", "mt_type", "sender_bic",
        "receiver_bic"),
    "OTHER": (
        "message_id",),
}


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class TradeNetwork(Enum):
    WE_TRADE = "WE_TRADE"
    MARCO_POLO = "MARCO_POLO"
    CONTOUR = "CONTOUR"
    BOLERO = "BOLERO"
    SWIFT_GPI = "SWIFT_GPI"
    SWIFT_FIN = "SWIFT_FIN"
    OTHER = "OTHER"


class MessageValidationStatus(Enum):
    VALID = "VALID"
    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    MALFORMED = "MALFORMED"
    UNKNOWN_PROTOCOL = "UNKNOWN_PROTOCOL"


class RoutingAction(Enum):
    NEW_LC_ISSUANCE = "NEW_LC_ISSUANCE"
    AMENDMENT_NOTIFICATION = "AMENDMENT_NOTIFICATION"
    DRAWDOWN_NOTIFICATION = "DRAWDOWN_NOTIFICATION"
    DOCUMENT_DISPATCH = "DOCUMENT_DISPATCH"
    STATUS_UPDATE = "STATUS_UPDATE"
    PAYMENT_INSTRUCTION = "PAYMENT_INSTRUCTION"
    UNKNOWN = "UNKNOWN"


class AnomalyType(Enum):
    DUPLICATE_MESSAGE_ID = "DUPLICATE_MESSAGE_ID"
    OUT_OF_SEQUENCE = "OUT_OF_SEQUENCE"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    UNKNOWN_SENDER = "UNKNOWN_SENDER"


class AnomalySeverity(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ════════════════════════════════════════════════════════════════════════
# Input + intermediate dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class InboundMessage:
    """A single inbound message from a trade network.

    body is the raw protocol-formatted dict; engine reads it
    via caller-supplied field mappings, never assumes structure
    beyond protocol-required fields.
    """
    message_id: str
    network: TradeNetwork
    received_at: date
    body: Mapping[str, Any]
    sequence_number: Optional[int] = None
    protocol_version: Optional[str] = None
    sender_id: Optional[str] = None


@dataclass(frozen=True)
class FieldMapping:
    """Caller-supplied per-network field mapping.

    inbound_field is the field name in the raw message body;
    internal_field is the canonical name the platform uses.
    """
    inbound_field: str
    internal_field: str
    is_required: bool = True


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class MessageValidationResult:
    message_id: str
    network: TradeNetwork
    status: MessageValidationStatus
    missing_fields: Tuple[str, ...]
    malformed_fields: Tuple[str, ...]
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class SchemaMappingResult:
    message_id: str
    network: TradeNetwork
    mapped_fields: Mapping[str, Any]
    unmapped_inbound_fields: Tuple[str, ...]
    missing_required_internal_fields: Tuple[str, ...]
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class RoutingActionClassification:
    message_id: str
    network: TradeNetwork
    action: RoutingAction
    matched_message_type: Optional[str]
    reasoning: str
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class ProtocolAnomaly:
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    message_ids: Tuple[str, ...]
    description: str
    context: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectivityReport:
    as_of_date: str
    total_messages: int
    by_network_count: Mapping[str, int]
    by_status_count: Mapping[str, int]
    by_action_count: Mapping[str, int]
    anomaly_count: int
    anomaly_count_by_type: Mapping[str, int]
    top_error_types: Tuple[Tuple[str, int], ...]
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TradeFinanceConnectivityEngine:
    """Diagnostic adapter surface for trade-finance networks."""

    def __init__(
        self,
        protocol_required_fields: Optional[
            Mapping[str, Sequence[str]]] = None,
        supported_versions: Optional[
            Mapping[str, Tuple[str, ...]]] = None,
        known_senders: Optional[Set[str]] = None,
    ) -> None:
        # When caller provides protocol_required_fields,
        # it REPLACES defaults entirely (caller-supplied data
        # discipline — same as ENH-274). When None, defaults
        # apply.
        if protocol_required_fields is None:
            self._protocol_required_fields: Dict[
                str, Tuple[str, ...]] = dict(
                DEFAULT_PROTOCOL_REQUIRED_FIELDS)
        else:
            self._protocol_required_fields = {
                k: tuple(v)
                for k, v in protocol_required_fields.items()}
        # Supported version map per protocol — caller-supplied;
        # when empty, version mismatch detection is disabled
        self._supported_versions: Dict[
            str, Tuple[str, ...]] = dict(
            supported_versions or {})
        # Known senders — for anomaly detection; empty disables
        self._known_senders: Set[str] = set(
            known_senders or ())

    # ─── 1. Validate inbound message structure ─────────────────
    def validate_inbound_message_structure(
        self, msg: InboundMessage,
    ) -> MessageValidationResult:
        protocol_key = msg.network.value
        required = self._protocol_required_fields.get(
            protocol_key)

        if required is None:
            return MessageValidationResult(
                message_id=msg.message_id,
                network=msg.network,
                status=(
                    MessageValidationStatus.UNKNOWN_PROTOCOL),
                missing_fields=(),
                malformed_fields=(),
                framework_refs=(
                    "ENH-276 §validate_inbound_message_"
                    "structure",
                    f"Network {msg.network.value} not in "
                    "configured protocol_required_fields — "
                    "extend via constructor",
                    "Per Rule 7 — engine never falls back to "
                    "guessing required fields; surfaces "
                    "UNKNOWN_PROTOCOL for operator action",
                ))

        missing: List[str] = []
        malformed: List[str] = []
        body = msg.body or {}
        for fld in required:
            if fld not in body:
                missing.append(fld)
                continue
            v = body[fld]
            if v is None or (
                isinstance(v, str) and v.strip() == ""
            ):
                malformed.append(fld)

        if missing:
            status = (
                MessageValidationStatus
                .MISSING_REQUIRED_FIELDS)
        elif malformed:
            status = MessageValidationStatus.MALFORMED
        else:
            status = MessageValidationStatus.VALID

        return MessageValidationResult(
            message_id=msg.message_id,
            network=msg.network,
            status=status,
            missing_fields=tuple(missing),
            malformed_fields=tuple(malformed),
            framework_refs=(
                "ENH-276 §validate_inbound_message_structure",
                f"Network: {msg.network.value}",
                f"Required fields per protocol: "
                f"{required}",
                "Per Rule 1 — full list of missing + "
                "malformed fields surfaced for operator",
                "Per Rule 7 — engine validates structure; "
                "never accepts/rejects the message itself",
            ),
        )

    # ─── 2. Map to internal schema ─────────────────────────────
    def map_to_internal_schema(
        self,
        msg: InboundMessage,
        field_mappings: Sequence[FieldMapping],
        required_internal_fields: Sequence[str] = (),
    ) -> SchemaMappingResult:
        """Project inbound fields onto internal schema.

        field_mappings — caller-supplied per-network mappings
        (operationally maintained — same discipline as ENH-274
        sanctions lists). Engine bundles no defaults.

        required_internal_fields — caller-supplied list of
        internal fields that must be populated for downstream
        processing. Missing surfaced explicitly per Rule 1.
        """
        mapped: Dict[str, Any] = {}
        body = msg.body or {}
        consumed_inbound: Set[str] = set()

        for fm in field_mappings:
            if fm.inbound_field in body:
                v = body[fm.inbound_field]
                if v is not None and not (
                    isinstance(v, str) and v.strip() == ""
                ):
                    mapped[fm.internal_field] = v
                    consumed_inbound.add(fm.inbound_field)

        unmapped_inbound = tuple(sorted(
            f for f in body.keys()
            if f not in consumed_inbound))
        missing_internal = tuple(
            f for f in required_internal_fields
            if f not in mapped)

        return SchemaMappingResult(
            message_id=msg.message_id,
            network=msg.network,
            mapped_fields=mapped,
            unmapped_inbound_fields=unmapped_inbound,
            missing_required_internal_fields=missing_internal,
            framework_refs=(
                "ENH-276 §map_to_internal_schema",
                "Caller-supplied field_mappings — "
                "operationally maintained per network "
                "protocol updates (we.trade / Marco Polo / "
                "Contour / Bolero versions evolve)",
                "Per Rule 1 — both unmapped inbound and "
                "missing internal fields surfaced; engine "
                "never silently drops or fabricates",
                "Per Rule 7 — engine projects via mappings "
                "only; never derives values not in source "
                "message",
            ),
        )

    # ─── 3. Classify routing action ────────────────────────────
    def classify_routing_action(
        self,
        msg: InboundMessage,
        message_type_field: str,
        action_map: Mapping[str, RoutingAction],
    ) -> RoutingActionClassification:
        """Classify based on message-type field + caller-supplied
        type → action map."""
        body = msg.body or {}
        msg_type = body.get(message_type_field)
        if msg_type is None or not isinstance(msg_type, str):
            return RoutingActionClassification(
                message_id=msg.message_id,
                network=msg.network,
                action=RoutingAction.UNKNOWN,
                matched_message_type=None,
                reasoning=(
                    f"message_type_field "
                    f"'{message_type_field}' missing or non-"
                    f"string in message body"),
                framework_refs=(
                    "ENH-276 §classify_routing_action",
                    "Per Rule 7 — UNKNOWN surfaced rather "
                    "than guessing; operator decides",
                ))

        action = action_map.get(
            msg_type, RoutingAction.UNKNOWN)
        return RoutingActionClassification(
            message_id=msg.message_id,
            network=msg.network,
            action=action,
            matched_message_type=msg_type,
            reasoning=(
                f"message_type='{msg_type}' → "
                f"action={action.value}"),
            framework_refs=(
                "ENH-276 §classify_routing_action",
                "Caller-supplied action_map — per-network "
                "type-to-action lookup table",
                "Per Rule 1 — matched_message_type surfaced "
                "for traceability",
                "Per Rule 7 — engine classifies; never "
                "executes the routed action",
            ),
        )

    # ─── 4. Detect protocol anomalies ──────────────────────────
    def detect_protocol_anomalies(
        self, messages: Sequence[InboundMessage],
    ) -> Tuple[ProtocolAnomaly, ...]:
        """Detect duplicates, out-of-order, version mismatches,
        unknown senders across a sequence of messages."""
        anomalies: List[ProtocolAnomaly] = []

        # Duplicate message_id detection
        id_to_messages: Dict[str, List[str]] = {}
        for m in messages:
            id_to_messages.setdefault(
                m.message_id, []).append(m.message_id)
        for mid, ids in id_to_messages.items():
            if len(ids) > 1:
                anomalies.append(ProtocolAnomaly(
                    anomaly_type=(
                        AnomalyType.DUPLICATE_MESSAGE_ID),
                    severity=AnomalySeverity.HIGH,
                    message_ids=tuple(ids),
                    description=(
                        f"message_id '{mid}' appears "
                        f"{len(ids)} times in batch"),
                    context={"count": str(len(ids))}))

        # Out-of-order sequence detection per (network, sender)
        by_stream: Dict[
            Tuple[str, str], List[InboundMessage]] = {}
        for m in messages:
            if m.sequence_number is None:
                continue
            key = (m.network.value, m.sender_id or "<none>")
            by_stream.setdefault(key, []).append(m)
        for key, stream in by_stream.items():
            # Order by received_at, check sequence monotonic
            stream_sorted = sorted(
                stream,
                key=lambda x: x.received_at)
            prev_seq: Optional[int] = None
            for m in stream_sorted:
                if (
                    prev_seq is not None
                    and m.sequence_number is not None
                    and m.sequence_number < prev_seq
                ):
                    anomalies.append(ProtocolAnomaly(
                        anomaly_type=(
                            AnomalyType.OUT_OF_SEQUENCE),
                        severity=AnomalySeverity.MEDIUM,
                        message_ids=(m.message_id,),
                        description=(
                            f"sequence_number "
                            f"{m.sequence_number} < previous "
                            f"{prev_seq} on network "
                            f"{key[0]} sender {key[1]}"),
                        context={
                            "stream_network": key[0],
                            "stream_sender": key[1],
                            "current_seq": str(
                                m.sequence_number),
                            "previous_seq": str(prev_seq)}))
                prev_seq = m.sequence_number

        # Version mismatch detection
        if self._supported_versions:
            for m in messages:
                if m.protocol_version is None:
                    continue
                supported = self._supported_versions.get(
                    m.network.value, ())
                if (
                    supported
                    and m.protocol_version not in supported
                ):
                    anomalies.append(ProtocolAnomaly(
                        anomaly_type=(
                            AnomalyType.VERSION_MISMATCH),
                        severity=AnomalySeverity.MEDIUM,
                        message_ids=(m.message_id,),
                        description=(
                            f"protocol_version "
                            f"'{m.protocol_version}' not in "
                            f"supported {supported} for "
                            f"network {m.network.value}"),
                        context={
                            "version": m.protocol_version,
                            "supported": str(supported)}))

        # Unknown sender detection
        if self._known_senders:
            for m in messages:
                if (
                    m.sender_id is not None
                    and m.sender_id not in self._known_senders
                ):
                    anomalies.append(ProtocolAnomaly(
                        anomaly_type=(
                            AnomalyType.UNKNOWN_SENDER),
                        severity=AnomalySeverity.MEDIUM,
                        message_ids=(m.message_id,),
                        description=(
                            f"sender_id '{m.sender_id}' not "
                            f"in configured known_senders"),
                        context={"sender_id": m.sender_id}))

        return tuple(anomalies)

    # ─── 5. Connectivity report orchestrator ───────────────────
    def build_connectivity_report(
        self,
        messages: Sequence[InboundMessage],
        as_of_date_iso: str,
        action_map_by_network: Optional[
            Mapping[
                TradeNetwork,
                Tuple[str, Mapping[str, RoutingAction]]]
        ] = None,
    ) -> ConnectivityReport:
        """Portfolio rollup across all 4 capabilities.

        action_map_by_network maps TradeNetwork → (message_type_
        field_name, type_to_action_map). When None, routing-
        action distribution shows all UNKNOWN.
        """
        action_map_by_network = action_map_by_network or {}

        by_network: Counter = Counter()
        by_status: Counter = Counter()
        by_action: Counter = Counter()
        error_types: Counter = Counter()

        for m in messages:
            by_network[m.network.value] += 1
            v = self.validate_inbound_message_structure(m)
            by_status[v.status.value] += 1

            for f in v.missing_fields:
                error_types[f"missing:{f}"] += 1
            for f in v.malformed_fields:
                error_types[f"malformed:{f}"] += 1

            if m.network in action_map_by_network:
                fld, amap = action_map_by_network[m.network]
                a = self.classify_routing_action(
                    m, fld, amap)
                by_action[a.action.value] += 1
            else:
                by_action[RoutingAction.UNKNOWN.value] += 1

        anomalies = self.detect_protocol_anomalies(messages)
        anom_by_type: Counter = Counter(
            a.anomaly_type.value for a in anomalies)

        top_errors = tuple(error_types.most_common(5))

        return ConnectivityReport(
            as_of_date=as_of_date_iso,
            total_messages=len(messages),
            by_network_count=dict(by_network),
            by_status_count=dict(by_status),
            by_action_count=dict(by_action),
            anomaly_count=len(anomalies),
            anomaly_count_by_type=dict(anom_by_type),
            top_error_types=top_errors,
            framework_refs=(
                "ENH-276 §build_connectivity_report",
                "Per-network message counts + validation "
                "outcome distribution + routing-action "
                "distribution + anomaly counts + top error "
                "types",
                "Per Rule 7 — report data only; cockpit "
                "renders; operator interprets; no auto-action",
            ),
        )


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_we_trade_message(
    mid="MT-1",
    body=None,
    received=date(2026, 5, 1),
    seq=1,
    version="2.0",
    sender="BANK-A",
):
    if body is None:
        body = {
            "message_id": mid,
            "message_type": "ISSUE_LC",
            "sender_bin": "BIN-A",
            "receiver_bin": "BIN-B",
            "lc_reference": "LC-001",
            "amount": "1000000",
            "currency": "USD",
            "version": "2.0"}
    return InboundMessage(
        message_id=mid,
        network=TradeNetwork.WE_TRADE,
        received_at=received,
        body=body,
        sequence_number=seq,
        protocol_version=version,
        sender_id=sender)


# ─── Validation tests ──────────────────────────────────────────

def _test_validate_we_trade_complete():
    eng = TradeFinanceConnectivityEngine()
    msg = _make_we_trade_message()
    r = eng.validate_inbound_message_structure(msg)
    assert r.status == MessageValidationStatus.VALID
    assert r.missing_fields == ()
    assert r.malformed_fields == ()


def _test_validate_missing_required_field():
    eng = TradeFinanceConnectivityEngine()
    body = {
        "message_id": "MT-2",
        "message_type": "ISSUE_LC",
        "sender_bin": "BIN-A",
        # Missing: receiver_bin, lc_reference, amount, currency, version
    }
    msg = _make_we_trade_message(mid="MT-2", body=body)
    r = eng.validate_inbound_message_structure(msg)
    assert r.status == (
        MessageValidationStatus.MISSING_REQUIRED_FIELDS)
    assert "receiver_bin" in r.missing_fields
    assert "lc_reference" in r.missing_fields
    assert "amount" in r.missing_fields


def _test_validate_malformed_empty_field():
    eng = TradeFinanceConnectivityEngine()
    body = {
        "message_id": "MT-3",
        "message_type": "ISSUE_LC",
        "sender_bin": "",     # empty string
        "receiver_bin": "BIN-B",
        "lc_reference": "LC-1",
        "amount": "100",
        "currency": "USD",
        "version": "2.0"}
    msg = _make_we_trade_message(mid="MT-3", body=body)
    r = eng.validate_inbound_message_structure(msg)
    assert r.status == MessageValidationStatus.MALFORMED
    assert "sender_bin" in r.malformed_fields


def _test_validate_unknown_protocol():
    """Network not in protocol_required_fields config."""
    eng = TradeFinanceConnectivityEngine(
        protocol_required_fields={})
    msg = _make_we_trade_message()
    r = eng.validate_inbound_message_structure(msg)
    assert r.status == (
        MessageValidationStatus.UNKNOWN_PROTOCOL)


def _test_validate_marco_polo():
    eng = TradeFinanceConnectivityEngine()
    body = {
        "message_id": "MP-1",
        "msg_type": "TRADE_INIT",
        "originator": "Bank-A",
        "destination": "Bank-B",
        "trade_id": "T-001",
        "amount": "500000",
        "currency": "EUR",
        "protocol_version": "3.1"}
    msg = InboundMessage(
        message_id="MP-1",
        network=TradeNetwork.MARCO_POLO,
        received_at=date(2026, 5, 1),
        body=body)
    r = eng.validate_inbound_message_structure(msg)
    assert r.status == MessageValidationStatus.VALID


# ─── Mapping tests ─────────────────────────────────────────────

def _test_mapping_basic():
    eng = TradeFinanceConnectivityEngine()
    msg = _make_we_trade_message()
    mappings = (
        FieldMapping("lc_reference", "lc_id"),
        FieldMapping("amount", "amount_kes"),
        FieldMapping("currency", "currency"),
        FieldMapping("sender_bin", "issuing_bank_bic"))
    r = eng.map_to_internal_schema(msg, mappings)
    assert r.mapped_fields["lc_id"] == "LC-001"
    assert r.mapped_fields["amount_kes"] == "1000000"
    assert r.mapped_fields["currency"] == "USD"
    # message_id, message_type, version, receiver_bin etc
    # are unmapped — should be surfaced
    assert "message_id" in r.unmapped_inbound_fields


def _test_mapping_missing_required_internal():
    eng = TradeFinanceConnectivityEngine()
    msg = _make_we_trade_message()
    mappings = (
        FieldMapping("lc_reference", "lc_id"),)
    r = eng.map_to_internal_schema(
        msg, mappings,
        required_internal_fields=(
            "lc_id", "amount_kes", "currency"))
    assert "amount_kes" in (
        r.missing_required_internal_fields)
    assert "currency" in (
        r.missing_required_internal_fields)
    # lc_id IS mapped so not in missing
    assert "lc_id" not in (
        r.missing_required_internal_fields)


def _test_mapping_skips_empty_values():
    eng = TradeFinanceConnectivityEngine()
    body = {"lc_reference": "", "amount": "100"}
    msg = InboundMessage(
        message_id="X",
        network=TradeNetwork.WE_TRADE,
        received_at=date(2026, 5, 1),
        body=body)
    mappings = (
        FieldMapping("lc_reference", "lc_id"),
        FieldMapping("amount", "amount_kes"))
    r = eng.map_to_internal_schema(msg, mappings)
    # Empty string skipped — not mapped
    assert "lc_id" not in r.mapped_fields
    assert r.mapped_fields["amount_kes"] == "100"


# ─── Routing classification tests ──────────────────────────────

def _test_routing_known_action():
    eng = TradeFinanceConnectivityEngine()
    msg = _make_we_trade_message()
    action_map = {
        "ISSUE_LC": RoutingAction.NEW_LC_ISSUANCE,
        "AMEND_LC": RoutingAction.AMENDMENT_NOTIFICATION}
    r = eng.classify_routing_action(
        msg, "message_type", action_map)
    assert r.action == RoutingAction.NEW_LC_ISSUANCE
    assert r.matched_message_type == "ISSUE_LC"


def _test_routing_unknown_action():
    eng = TradeFinanceConnectivityEngine()
    msg = _make_we_trade_message()
    msg_with_unknown = InboundMessage(
        message_id=msg.message_id,
        network=msg.network,
        received_at=msg.received_at,
        body={**msg.body, "message_type": "WEIRD_NEW_TYPE"},
        sequence_number=msg.sequence_number)
    r = eng.classify_routing_action(
        msg_with_unknown, "message_type",
        {"ISSUE_LC": RoutingAction.NEW_LC_ISSUANCE})
    assert r.action == RoutingAction.UNKNOWN
    assert r.matched_message_type == "WEIRD_NEW_TYPE"


def _test_routing_field_missing():
    eng = TradeFinanceConnectivityEngine()
    body = {"message_id": "X"}    # no message_type
    msg = InboundMessage(
        message_id="X",
        network=TradeNetwork.WE_TRADE,
        received_at=date(2026, 5, 1),
        body=body)
    r = eng.classify_routing_action(
        msg, "message_type", {})
    assert r.action == RoutingAction.UNKNOWN
    assert r.matched_message_type is None


# ─── Anomaly detection tests ───────────────────────────────────

def _test_anomaly_duplicate_message_id():
    eng = TradeFinanceConnectivityEngine()
    msgs = (
        _make_we_trade_message(mid="DUP-1", seq=1),
        _make_we_trade_message(
            mid="DUP-1",   # same id
            received=date(2026, 5, 2), seq=2),
    )
    a = eng.detect_protocol_anomalies(msgs)
    assert any(
        x.anomaly_type == AnomalyType.DUPLICATE_MESSAGE_ID
        for x in a)


def _test_anomaly_out_of_sequence():
    eng = TradeFinanceConnectivityEngine()
    msgs = (
        _make_we_trade_message(
            mid="A", received=date(2026, 5, 1), seq=10),
        _make_we_trade_message(
            mid="B", received=date(2026, 5, 2), seq=5),
    )
    a = eng.detect_protocol_anomalies(msgs)
    assert any(
        x.anomaly_type == AnomalyType.OUT_OF_SEQUENCE
        for x in a)


def _test_anomaly_version_mismatch():
    eng = TradeFinanceConnectivityEngine(
        supported_versions={"WE_TRADE": ("2.0", "2.1")})
    msgs = (
        _make_we_trade_message(version="3.0"),)
    a = eng.detect_protocol_anomalies(msgs)
    assert any(
        x.anomaly_type == AnomalyType.VERSION_MISMATCH
        for x in a)


def _test_anomaly_unknown_sender():
    eng = TradeFinanceConnectivityEngine(
        known_senders={"BANK-A", "BANK-B"})
    msgs = (
        _make_we_trade_message(sender="ROGUE-SENDER"),)
    a = eng.detect_protocol_anomalies(msgs)
    assert any(
        x.anomaly_type == AnomalyType.UNKNOWN_SENDER
        for x in a)


def _test_anomaly_clean_no_findings():
    eng = TradeFinanceConnectivityEngine()
    msgs = (
        _make_we_trade_message(mid="A", seq=1),
        _make_we_trade_message(
            mid="B", received=date(2026, 5, 2), seq=2),
    )
    a = eng.detect_protocol_anomalies(msgs)
    assert a == ()


# ─── Connectivity report tests ─────────────────────────────────

def _test_connectivity_report_basic():
    eng = TradeFinanceConnectivityEngine()
    msgs = (
        _make_we_trade_message(mid="A", seq=1),
        _make_we_trade_message(
            mid="B", received=date(2026, 5, 2), seq=2),
        _make_we_trade_message(
            mid="C", received=date(2026, 5, 3), seq=3,
            body={
                "message_id": "C",
                "message_type": "ISSUE_LC",
                "sender_bin": "X",
                # missing receiver_bin
                "lc_reference": "LC-3",
                "amount": "100",
                "currency": "USD",
                "version": "2.0"}),
    )
    action_map = {
        TradeNetwork.WE_TRADE: (
            "message_type",
            {"ISSUE_LC": RoutingAction.NEW_LC_ISSUANCE})}
    r = eng.build_connectivity_report(
        msgs,
        as_of_date_iso="2026-05-03",
        action_map_by_network=action_map)
    assert r.total_messages == 3
    assert r.by_network_count["WE_TRADE"] == 3
    assert r.by_status_count[
        MessageValidationStatus.VALID.value] == 2
    assert r.by_status_count[
        MessageValidationStatus
        .MISSING_REQUIRED_FIELDS.value] == 1
    assert r.by_action_count[
        RoutingAction.NEW_LC_ISSUANCE.value] == 3
    assert (
        ("missing:receiver_bin", 1) in r.top_error_types)


def _test_connectivity_report_empty():
    eng = TradeFinanceConnectivityEngine()
    r = eng.build_connectivity_report(
        (), as_of_date_iso="2026-05-03")
    assert r.total_messages == 0
    assert r.anomaly_count == 0
    assert r.top_error_types == ()


# ─── Discipline tests ──────────────────────────────────────────

def _test_engine_does_not_mutate_inputs():
    eng = TradeFinanceConnectivityEngine()
    msg = _make_we_trade_message()
    eng.validate_inbound_message_structure(msg)
    eng.classify_routing_action(msg, "message_type", {})
    # Inputs unchanged
    assert msg.message_id == "MT-1"
    assert msg.body["lc_reference"] == "LC-001"


def _test_full_provenance():
    eng = TradeFinanceConnectivityEngine()
    msg = _make_we_trade_message()
    r = eng.validate_inbound_message_structure(msg)
    refs = " / ".join(r.framework_refs)
    assert "ENH-276" in refs
    assert "Rule 1" in refs
    assert "Rule 7" in refs


def _test_caller_supplied_data_discipline():
    """Engine should work with empty mappings — bundles no
    defaults beyond protocol-required field specs."""
    eng = TradeFinanceConnectivityEngine()
    msg = _make_we_trade_message()
    r = eng.map_to_internal_schema(msg, ())
    # Empty mappings → empty mapped, all inbound unmapped
    assert r.mapped_fields == {}
    assert len(r.unmapped_inbound_fields) >= 5


def self_test() -> None:
    tests = [
        _test_validate_we_trade_complete,
        _test_validate_missing_required_field,
        _test_validate_malformed_empty_field,
        _test_validate_unknown_protocol,
        _test_validate_marco_polo,
        _test_mapping_basic,
        _test_mapping_missing_required_internal,
        _test_mapping_skips_empty_values,
        _test_routing_known_action,
        _test_routing_unknown_action,
        _test_routing_field_missing,
        _test_anomaly_duplicate_message_id,
        _test_anomaly_out_of_sequence,
        _test_anomaly_version_mismatch,
        _test_anomaly_unknown_sender,
        _test_anomaly_clean_no_findings,
        _test_connectivity_report_basic,
        _test_connectivity_report_empty,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
        _test_caller_supplied_data_discipline,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append(
                (t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ trade_finance_connectivity self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trade_finance_connectivity self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
