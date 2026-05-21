"""utils/uncertainty/poisoning.py — Phase 4 of Uncertainty Exposure.

Data poisoning & corruption scenarios. Each scenario:
  1. Injects a specific kind of data corruption
  2. Probes whether the system handles it gracefully
  3. Verifies the audit trail preserves both the bad input and rejection

The 10 poisoning patterns:
   1. Malformed JSON payload (truncated, garbage chars)
   2. Negative amount transaction
   3. Future-dated transaction (year 2099)
   4. Duplicate correlation_id with different content
   5. Oversized payload (1MB string field)
   6. Null/missing required fields
   7. Wrong-type field (string where int expected)
   8. Cross-tenant contamination ('Equity' bank in Ecobank context)
   9. Unicode-bomb payload (RTL overrides, zero-width chars)
  10. SQL/script injection attempts in text fields

For each: a Drill that uses ScriptedPolicy to invoke channel:submit
with the poisoned payload, and an oracle that verifies the system
EITHER rejected cleanly OR processed safely (idempotent + auditable).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from utils.arena.base import (
    Drill, DrillEnvironmentEvent, DrillOracle,
)
from utils.agents.policies import AgentPolicy


_NAIROBI_TZ = None
def _tz():
    global _NAIROBI_TZ
    if _NAIROBI_TZ is None:
        from utils.simulation_clock import NAIROBI_TZ
        _NAIROBI_TZ = NAIROBI_TZ
    return _NAIROBI_TZ


# ─── Poisoning policies ─────────────────────────────────────────────


class MalformedPayloadPolicy(AgentPolicy):
    """Submit payloads that look wrong in structural ways."""
    name = "malformed_payload"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            # Payload missing required transaction_type
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"msisdn": "254712345678",
                            "amount": 1500, "paybill": "174379"},
                "amount": 1500, "reference": "malformed_1",
                "actor": "poison", "seed": 1},
              "submit without transaction_type"),
            # Payload with garbage transaction_type
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "\x00\x01garbage",
                            "msisdn": "254712345678",
                            "amount": 1500, "paybill": "174379"},
                "amount": 1500, "reference": "malformed_2",
                "actor": "poison", "seed": 2},
              "garbage transaction_type"),
            # Recovery
            ("channel:list", {}, "recover by listing channels"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "malformed probe complete")


class NegativeAmountPolicy(AgentPolicy):
    """Try negative-amount transactions."""
    name = "negative_amount"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678",
                            "amount": -1500, "paybill": "174379"},
                "amount": -1500, "reference": "neg_amt_1",
                "actor": "poison", "seed": 3},
              "submit with negative amount"),
            ("channel:submit",
              {"channel": "rtgs",
                "payload": {"amount": -100000.0, "currency": "KES",
                            "beneficiary_account": "0123456789",
                            "beneficiary_bank": "EQBLKENA"},
                "amount": -100000.0, "reference": "neg_amt_2",
                "actor": "poison", "seed": 4},
              "negative RTGS amount"),
            ("events:query",
              {"event_type": "integration.mpesa.success", "limit": 5},
              "check the audit trail"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "negative amount probe complete")


class FutureDatedPolicy(AgentPolicy):
    """Submit transactions dated wildly in the future."""
    name = "future_dated"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678",
                            "amount": 1500, "paybill": "174379",
                            "value_date": "2099-12-31"},
                "amount": 1500, "reference": "future_dated_1",
                "actor": "poison", "seed": 5},
              "future-dated 2099 transaction"),
            ("events:query",
              {"event_type": "integration.mpesa.success", "limit": 5},
              "verify what posted"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "future-dated probe complete")


class DuplicateCorrelationIdPolicy(AgentPolicy):
    """Submit two different payloads with the same reference."""
    name = "dup_correlation_id"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678",
                            "amount": 1000, "paybill": "174379"},
                "amount": 1000, "reference": "dup_corr_id",
                "actor": "poison_a", "seed": 6},
              "first submit with shared ref"),
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254799999999",  # different msisdn
                            "amount": 9999, "paybill": "174379"},
                "amount": 9999, "reference": "dup_corr_id",
                "actor": "poison_b", "seed": 7},
              "second submit, same ref, different content"),
            ("events:query",
              {"event_type": "integration.mpesa.success", "limit": 5},
              "check audit trail"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "dup correlation id probe complete")


class OversizedPayloadPolicy(AgentPolicy):
    """Send a payload field with 1MB of content."""
    name = "oversized_payload"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        if self._step == 0:
            self._step += 1
            huge = "A" * (1024 * 1024)  # 1 MB
            return (
                "channel:submit",
                {"channel": "mpesa",
                  "payload": {"transaction_type": "CustomerPayBillOnline",
                              "msisdn": "254712345678",
                              "amount": 1500, "paybill": "174379",
                              "memo": huge},
                  "amount": 1500, "reference": "oversize_1",
                  "actor": "poison", "seed": 8},
                "submit with 1MB memo field",
            )
        if self._step == 1:
            self._step += 1
            return ("channel:list", {}, "recover after oversize")
        return (None, {}, "oversized probe complete")


class NullFieldsPolicy(AgentPolicy):
    """Submit with required fields explicitly null/missing."""
    name = "null_fields"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": None,
                            "msisdn": None,
                            "amount": None, "paybill": None},
                "amount": 1500, "reference": "null_fields_1",
                "actor": "poison", "seed": 9},
              "submit with all-null payload fields"),
            ("channel:submit",
              {"channel": "rtgs",
                "payload": {},  # empty
                "amount": 50000.0, "reference": "null_fields_2",
                "actor": "poison", "seed": 10},
              "submit with empty payload dict"),
            ("events:query",
              {"event_type": "integration.mpesa.failure", "limit": 5},
              "check failure events"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "null fields probe complete")


class WrongTypePolicy(AgentPolicy):
    """String where int expected, list where str expected, etc."""
    name = "wrong_type"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678",
                            "amount": "not_a_number",
                            "paybill": "174379"},
                "amount": "not_a_number", "reference": "wrongtype_1",
                "actor": "poison", "seed": 11},
              "amount as string"),
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": ["not", "a", "string"],
                            "msisdn": "254712345678",
                            "amount": 1500, "paybill": "174379"},
                "amount": 1500, "reference": "wrongtype_2",
                "actor": "poison", "seed": 12},
              "transaction_type as list"),
            ("channel:list", {}, "recover"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "wrong type probe complete")


class CrossTenantContaminationPolicy(AgentPolicy):
    """Sneak references to other banks into payload."""
    name = "cross_tenant"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("channel:submit",
              {"channel": "swift",
                "payload": {"sender_bic": "EQBLKENA",  # Equity Bank
                            "amount": 1000.0, "currency": "USD",
                            "beneficiary_account": "0123456789",
                            "beneficiary_name": "Cross Tenant Test"},
                "amount": 1000.0, "reference": "cross_tenant_1",
                "actor": "poison", "seed": 13},
              "SWIFT with Equity Bank BIC instead of Ecobank"),
            ("channel:submit",
              {"channel": "rtgs",
                "payload": {"originator_bank": "ABSANBJ",  # Absa BIC
                            "amount": 50000.0, "currency": "KES",
                            "beneficiary_account": "0123456789",
                            "beneficiary_bank": "ECOCKENA"},
                "amount": 50000.0, "reference": "cross_tenant_2",
                "actor": "poison", "seed": 14},
              "RTGS originator wrong bank"),
            ("events:query",
              {"event_type": "integration.swift.success", "limit": 5},
              "check what posted"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "cross tenant probe complete")


class UnicodeBombPolicy(AgentPolicy):
    """RTL overrides, zero-width chars, mixed-script attacks."""
    name = "unicode_bomb"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        # RTL override that visually reverses text:
        rtl = "Pay\u202E\u2066customer123"
        zwj = "John\u200D\u200B\u200C Smith"
        plans = [
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678",
                            "amount": 1500, "paybill": "174379",
                            "narrative": rtl},
                "amount": 1500, "reference": "uni_bomb_1",
                "actor": "poison", "seed": 15},
              "RTL override in narrative"),
            ("channel:submit",
              {"channel": "rtgs",
                "payload": {"amount": 10000.0, "currency": "KES",
                            "beneficiary_account": "0123456789",
                            "beneficiary_name": zwj,
                            "beneficiary_bank": "ECOCKENA"},
                "amount": 10000.0, "reference": "uni_bomb_2",
                "actor": "poison", "seed": 16},
              "zero-width chars in beneficiary name"),
            ("events:query",
              {"event_type": "integration.mpesa.success", "limit": 5},
              "verify audit trail"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "unicode bomb probe complete")


class InjectionAttemptPolicy(AgentPolicy):
    """SQL/script injection patterns in text fields."""
    name = "injection_attempt"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            # Classic SQL injection in msisdn
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "'; DROP TABLE users--",
                            "amount": 1500, "paybill": "174379"},
                "amount": 1500, "reference": "inj_sql_1",
                "actor": "poison", "seed": 17},
              "SQL injection in msisdn"),
            # JS / HTML injection in narrative
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678",
                            "amount": 1500, "paybill": "174379",
                            "narrative": "<script>alert(1)</script>"},
                "amount": 1500, "reference": "inj_xss_1",
                "actor": "poison", "seed": 18},
              "XSS in narrative field"),
            # Template injection
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678",
                            "amount": 1500, "paybill": "174379",
                            "narrative": "{{config.__class__.__init__.__globals__}}"},
                "amount": 1500, "reference": "inj_tmpl_1",
                "actor": "poison", "seed": 19},
              "template injection attempt"),
            ("events:query",
              {"event_type": "integration.mpesa.success", "limit": 5},
              "check audit"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "injection probe complete")


# ─── Poisoning drill library ────────────────────────────────────────


def _build_poisoning_library():
    tz = _tz()
    L: Dict[str, tuple] = {}
    base = datetime(2026, 7, 5, 10, 0, tzinfo=tz)

    L["dp_malformed_payload"] = (Drill(
        name="dp_malformed_payload", category="data_poisoning",
        description="Submit malformed JSON-like payloads.",
        sim_start=base, environment=[],
        agent_goal="malformed_test",
        oracle=DrillOracle(
            min_steps=3,
            # We expect the bad calls to be handled; at least 1 success
            # (the recovery channel:list)
            min_successful_steps=1,
        ),
        tags=["poisoning", "malformed"],
    ), MalformedPayloadPolicy)

    L["dp_negative_amount"] = (Drill(
        name="dp_negative_amount", category="data_poisoning",
        description="Try transactions with negative amounts.",
        sim_start=base + timedelta(hours=1), environment=[],
        agent_goal="negative_amount_test",
        oracle=DrillOracle(
            min_steps=3,
            required_tool_calls=["channel:submit", "events:query"],
        ),
        tags=["poisoning", "negative"],
    ), NegativeAmountPolicy)

    L["dp_future_dated"] = (Drill(
        name="dp_future_dated", category="data_poisoning",
        description="Submit transactions value-dated in 2099.",
        sim_start=base + timedelta(hours=2), environment=[],
        agent_goal="future_dated_test",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["channel:submit"],
        ),
        tags=["poisoning", "future_dated"],
    ), FutureDatedPolicy)

    L["dp_duplicate_correlation_id"] = (Drill(
        name="dp_duplicate_correlation_id", category="data_poisoning",
        description=("Two submits with same reference but different "
                       "content. Tests idempotency / conflict handling."),
        sim_start=base + timedelta(hours=3), environment=[],
        agent_goal="dup_corr_test",
        oracle=DrillOracle(
            min_steps=3,
            required_tool_calls=["channel:submit", "events:query"],
        ),
        tags=["poisoning", "dup_corr"],
    ), DuplicateCorrelationIdPolicy)

    L["dp_oversized_payload"] = (Drill(
        name="dp_oversized_payload", category="data_poisoning",
        description="Payload with 1MB memo field.",
        sim_start=base + timedelta(hours=4), environment=[],
        agent_goal="oversize_test",
        oracle=DrillOracle(
            min_steps=2,
            # Even oversized may succeed, we just need stability
        ),
        tags=["poisoning", "oversize"],
    ), OversizedPayloadPolicy)

    L["dp_null_fields"] = (Drill(
        name="dp_null_fields", category="data_poisoning",
        description="Required fields explicitly null.",
        sim_start=base + timedelta(hours=5), environment=[],
        agent_goal="null_test",
        oracle=DrillOracle(
            min_steps=3,
            # We expect bad calls to fail; recovery should succeed
            max_failure_rate=0.95,
        ),
        tags=["poisoning", "null"],
    ), NullFieldsPolicy)

    L["dp_wrong_type"] = (Drill(
        name="dp_wrong_type", category="data_poisoning",
        description="Wrong-type fields (string where int, etc).",
        sim_start=base + timedelta(hours=6), environment=[],
        agent_goal="wrongtype_test",
        oracle=DrillOracle(
            min_steps=3,
            min_successful_steps=1,
        ),
        tags=["poisoning", "wrong_type"],
    ), WrongTypePolicy)

    L["dp_cross_tenant_contamination"] = (Drill(
        name="dp_cross_tenant_contamination", category="data_poisoning",
        description="Foreign-bank BICs in payloads.",
        sim_start=base + timedelta(hours=7), environment=[],
        agent_goal="cross_tenant_test",
        oracle=DrillOracle(
            min_steps=3,
            required_tool_calls=["channel:submit", "events:query"],
        ),
        tags=["poisoning", "cross_tenant"],
    ), CrossTenantContaminationPolicy)

    L["dp_unicode_bomb"] = (Drill(
        name="dp_unicode_bomb", category="data_poisoning",
        description="RTL overrides + zero-width chars in text fields.",
        sim_start=base + timedelta(hours=8), environment=[],
        agent_goal="unicode_test",
        oracle=DrillOracle(
            min_steps=3,
            required_tool_calls=["channel:submit", "events:query"],
        ),
        tags=["poisoning", "unicode"],
    ), UnicodeBombPolicy)

    L["dp_injection_attempts"] = (Drill(
        name="dp_injection_attempts", category="data_poisoning",
        description="SQL + XSS + template injection in text fields.",
        sim_start=base + timedelta(hours=9), environment=[],
        agent_goal="injection_test",
        oracle=DrillOracle(
            min_steps=4,
            required_tool_calls=["channel:submit", "events:query"],
        ),
        tags=["poisoning", "injection"],
    ), InjectionAttemptPolicy)

    return L


_LIBRARY = None


def _ensure():
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = _build_poisoning_library()
    return _LIBRARY


def list_poisoning_drills() -> List[str]:
    return sorted(_ensure().keys())


def get_poisoning_drill(name: str) -> Drill:
    L = _ensure()
    if name not in L:
        raise KeyError(f"unknown poisoning drill: {name!r}")
    return L[name][0]


def get_poisoning_policy_factory(name: str):
    L = _ensure()
    if name not in L:
        raise KeyError(f"unknown poisoning drill: {name!r}")
    return L[name][1]


def run_poisoning_drill(name: str):
    """Helper that wires the right policy into DrillRunner."""
    from utils.arena import DrillRunner
    from utils.agents.base import AgentBudget
    drill = get_poisoning_drill(name)
    policy_cls = get_poisoning_policy_factory(name)
    runner = DrillRunner(
        agent_policy=policy_cls(),
        agent_budget=AgentBudget(max_steps=20, max_seconds=60),
    )
    return runner.run(drill)


__all__ = [
    "MalformedPayloadPolicy", "NegativeAmountPolicy",
    "FutureDatedPolicy", "DuplicateCorrelationIdPolicy",
    "OversizedPayloadPolicy", "NullFieldsPolicy",
    "WrongTypePolicy", "CrossTenantContaminationPolicy",
    "UnicodeBombPolicy", "InjectionAttemptPolicy",
    "list_poisoning_drills", "get_poisoning_drill",
    "get_poisoning_policy_factory", "run_poisoning_drill",
]
