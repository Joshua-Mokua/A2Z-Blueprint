"""
================================================================================
A2Z MIS 360 — Standard #81: Internal Audit Universe & Risk-Based Audit Planning
================================================================================

Risk classification: Cat B (deterministic risk-based audit planning per IIA/CBK)

Computes audit universe + risk-based audit plan per IIA Standards + CBK PG/15:
    - inherent_risk_score(...)              -- weighted inherent risk per entity
    - control_environment_score(...)        -- control effectiveness rating
    - residual_risk_score(...)              -- inherent × (1 - control)
    - assign_risk_tier(...)                 -- HIGH / MEDIUM / LOW classification
    - generate_audit_plan(...)              -- 3-year rolling audit calendar
    - audit_universe_summary(...)           -- coverage metrics

IIA + CBK PG/15 risk tiers byte-for-byte:
    HIGH    : residual >= 70 — audit annually
    MEDIUM  : 40 <= residual < 70 — audit biennially (every 2 years)
    LOW     : residual < 40 — audit triennially (every 3 years)

Inherent risk factors (weighted) byte-for-byte:
    financial_materiality_kes (30%)
    transaction_volume       (15%)
    regulatory_exposure      (20%)
    fraud_susceptibility     (15%)
    process_complexity       (10%)
    change_velocity          (10%)

Control environment ratings (5-tier):
    EFFECTIVE        : 90-100 — full reliance possible
    LARGELY_EFFECTIVE: 70-89  — minor compensating controls needed
    PARTIALLY_EFFECTIVE: 50-69 — significant gaps
    INEFFECTIVE      : 25-49  — major remediation required
    NON_EXISTENT     : 0-24   — control absent

Honesty rules applied:
    Rule 1: residual_risk = None when inherent_score is None
    Rule 6: entities with missing risk factors excluded with count surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# Risk tier thresholds byte-for-byte (IIA + CBK PG/15)
HIGH_RISK_THRESHOLD = Decimal("70")
MEDIUM_RISK_THRESHOLD = Decimal("40")
RISK_TIERS: Tuple[str, ...] = ("HIGH", "MEDIUM", "LOW")

# Audit frequency by risk tier (months)
AUDIT_FREQUENCY_MONTHS: Dict[str, int] = {
    "HIGH": 12,    # annual
    "MEDIUM": 24,  # biennial
    "LOW": 36,     # triennial
}

# Inherent risk factor weights byte-for-byte (sum to 100)
INHERENT_RISK_WEIGHTS_PCT: Dict[str, Decimal] = {
    "financial_materiality_kes": Decimal("30"),
    "transaction_volume": Decimal("15"),
    "regulatory_exposure": Decimal("20"),
    "fraud_susceptibility": Decimal("15"),
    "process_complexity": Decimal("10"),
    "change_velocity": Decimal("10"),
}

# Control environment ratings byte-for-byte
CONTROL_RATINGS: Tuple[str, ...] = (
    "EFFECTIVE",
    "LARGELY_EFFECTIVE",
    "PARTIALLY_EFFECTIVE",
    "INEFFECTIVE",
    "NON_EXISTENT",
)

CONTROL_RATING_BANDS: Dict[str, Tuple[Decimal, Decimal]] = {
    "EFFECTIVE": (Decimal("90"), Decimal("100")),
    "LARGELY_EFFECTIVE": (Decimal("70"), Decimal("89")),
    "PARTIALLY_EFFECTIVE": (Decimal("50"), Decimal("69")),
    "INEFFECTIVE": (Decimal("25"), Decimal("49")),
    "NON_EXISTENT": (Decimal("0"), Decimal("24")),
}

# Auditable entity types
ENTITY_TYPES: Tuple[str, ...] = (
    "BRANCH",
    "DEPARTMENT",
    "PROCESS",
    "SUBSIDIARY",
    "IT_SYSTEM",
    "PRODUCT_LINE",
)

# Materiality bucketing (financial materiality factor)
# Maps KES value to 0-100 scale (for risk scoring)
MATERIALITY_THRESHOLDS_KES: List[Tuple[Decimal, Decimal]] = [
    (Decimal("100000000"), Decimal("100")),       # >=100M = max
    (Decimal("50000000"), Decimal("80")),
    (Decimal("10000000"), Decimal("60")),
    (Decimal("1000000"), Decimal("40")),
    (Decimal("100000"), Decimal("20")),
    (Decimal("0"), Decimal("0")),
]


@dataclass
class AuditableEntity:
    entity_id: str
    entity_name: str
    entity_type: str  # uses ENTITY_TYPES
    financial_materiality_kes: Optional[Decimal] = None  # asset/exposure value
    transaction_volume: Optional[Decimal] = None  # 0-100 scale
    regulatory_exposure: Optional[Decimal] = None  # 0-100 scale
    fraud_susceptibility: Optional[Decimal] = None  # 0-100 scale
    process_complexity: Optional[Decimal] = None  # 0-100 scale
    change_velocity: Optional[Decimal] = None  # 0-100 scale
    control_score: Optional[Decimal] = None  # 0-100 control effectiveness
    last_audit_date: Optional[date] = None


def _materiality_to_score(materiality_kes: Decimal) -> Decimal:
    """Convert KES materiality to 0-100 score using fixed thresholds."""
    for threshold, score in MATERIALITY_THRESHOLDS_KES:
        if materiality_kes >= threshold:
            return score
    return Decimal("0")


def _control_rating_for_score(score: Decimal) -> str:
    """Map numeric control score to rating band."""
    for rating, (lo, hi) in CONTROL_RATING_BANDS.items():
        if lo <= score <= hi:
            return rating
    return "NON_EXISTENT"


class AuditUniverseEngine:
    """Deterministic risk-based audit planning per IIA + CBK PG/15."""

    @staticmethod
    def inherent_risk_score(entity: AuditableEntity) -> Dict[str, Any]:
        """
        Compute weighted inherent risk score (0-100).
        Rule 6: missing factors excluded from score with count surfaced.
        """
        # Convert materiality KES to 0-100 score
        if entity.financial_materiality_kes is None:
            mat_score = None
        else:
            mat_score = _materiality_to_score(entity.financial_materiality_kes)

        factor_scores = {
            "financial_materiality_kes": mat_score,
            "transaction_volume": entity.transaction_volume,
            "regulatory_exposure": entity.regulatory_exposure,
            "fraud_susceptibility": entity.fraud_susceptibility,
            "process_complexity": entity.process_complexity,
            "change_velocity": entity.change_velocity,
        }

        present_factors = {k: v for k, v in factor_scores.items() if v is not None}
        missing_factors = [k for k, v in factor_scores.items() if v is None]

        if not present_factors:
            return {
                "entity_id": entity.entity_id,
                "inherent_risk_score": None,
                "missing_factors": missing_factors,
                "reason": "all_risk_factors_missing",
            }

        # Re-normalise weights so present factors sum to 100
        total_weight_present = sum(INHERENT_RISK_WEIGHTS_PCT[k]
                                    for k in present_factors)
        if total_weight_present <= 0:
            return {
                "entity_id": entity.entity_id,
                "inherent_risk_score": None,
                "reason": "zero_total_weight",
            }

        score = Decimal("0")
        for factor, value in present_factors.items():
            weight = INHERENT_RISK_WEIGHTS_PCT[factor]
            normalised = weight / total_weight_present * Decimal("100")
            score += value * normalised / Decimal("100")

        return {
            "entity_id": entity.entity_id,
            "inherent_risk_score": str(score.quantize(Decimal("0.01"))),
            "factor_count_used": len(present_factors),
            "missing_factors": missing_factors,
        }

    @staticmethod
    def control_environment_score(score: Optional[Decimal]) -> Dict[str, Any]:
        """Map numeric control score to IIA 5-tier rating."""
        if score is None:
            return {
                "control_score": None,
                "control_rating": None,
                "reason": "control_score_missing",
            }
        if score < 0 or score > 100:
            return {"error": f"score_out_of_range:{score}"}
        rating = _control_rating_for_score(score)
        return {
            "control_score": str(score.quantize(Decimal("0.01"))),
            "control_rating": rating,
        }

    @classmethod
    def residual_risk_score(cls, entity: AuditableEntity) -> Dict[str, Any]:
        """
        Residual = Inherent × (1 - Control/100).
        Rule 1: residual=None when inherent is None.
        """
        inherent = cls.inherent_risk_score(entity)
        if inherent.get("inherent_risk_score") is None:
            return {
                "entity_id": entity.entity_id,
                "inherent_risk_score": None,
                "control_score": (str(entity.control_score) if entity.control_score
                                  is not None else None),
                "residual_risk_score": None,
                "reason": inherent.get("reason", "inherent_unavailable"),
            }
        inherent_val = Decimal(inherent["inherent_risk_score"])
        if entity.control_score is None:
            # Default to no control (worst case) — residual = inherent
            residual = inherent_val
            control_basis = "no_control_data_assumed_no_mitigation"
        else:
            control_factor = (Decimal("100") - entity.control_score) / Decimal("100")
            residual = inherent_val * control_factor
            control_basis = "control_score_applied"

        risk_tier = (
            "HIGH" if residual >= HIGH_RISK_THRESHOLD
            else "MEDIUM" if residual >= MEDIUM_RISK_THRESHOLD
            else "LOW"
        )
        return {
            "entity_id": entity.entity_id,
            "inherent_risk_score": inherent["inherent_risk_score"],
            "control_score": (str(entity.control_score.quantize(Decimal("0.01")))
                              if entity.control_score is not None else None),
            "residual_risk_score": str(residual.quantize(Decimal("0.01"))),
            "risk_tier": risk_tier,
            "control_basis": control_basis,
            "audit_frequency_months": AUDIT_FREQUENCY_MONTHS[risk_tier],
        }

    @classmethod
    def generate_audit_plan(
        cls,
        entities: List[AuditableEntity],
        plan_start: date,
        plan_horizon_years: int = 3,
    ) -> Dict[str, Any]:
        """
        Generate rolling audit plan over horizon.
        Each entity scheduled per its risk-tier frequency.
        """
        plan_end = date(plan_start.year + plan_horizon_years,
                        plan_start.month, plan_start.day)
        scheduled = []
        excluded = []

        for e in entities:
            rr = cls.residual_risk_score(e)
            if rr.get("residual_risk_score") is None:
                excluded.append(e.entity_id)
                continue
            tier = rr["risk_tier"]
            freq_months = AUDIT_FREQUENCY_MONTHS[tier]
            # Last audit date or plan_start
            cur = e.last_audit_date or plan_start
            # Roll forward by frequency until past plan_start
            while cur < plan_start:
                cur = date(
                    cur.year + (cur.month + freq_months - 1) // 12,
                    ((cur.month + freq_months - 1) % 12) + 1,
                    cur.day if cur.day <= 28 else 28,
                )
            # Schedule audits within horizon
            while cur < plan_end:
                scheduled.append({
                    "entity_id": e.entity_id,
                    "entity_name": e.entity_name,
                    "scheduled_date": cur.isoformat(),
                    "risk_tier": tier,
                    "residual_risk_score": rr["residual_risk_score"],
                })
                cur = date(
                    cur.year + (cur.month + freq_months - 1) // 12,
                    ((cur.month + freq_months - 1) % 12) + 1,
                    cur.day if cur.day <= 28 else 28,
                )

        # Sort scheduled by date
        scheduled.sort(key=lambda x: (x["scheduled_date"], x["entity_id"]))

        return {
            "plan_start": plan_start.isoformat(),
            "plan_end": plan_end.isoformat(),
            "horizon_years": plan_horizon_years,
            "scheduled_audits": scheduled,
            "scheduled_count": len(scheduled),
            "excluded_entities": excluded,
            "excluded_count": len(excluded),
        }

    @classmethod
    def audit_universe_summary(
        cls,
        entities: List[AuditableEntity],
    ) -> Dict[str, Any]:
        """Summary metrics across audit universe."""
        tier_counts = {t: 0 for t in RISK_TIERS}
        type_counts = {t: 0 for t in ENTITY_TYPES}
        excluded = []
        for e in entities:
            if e.entity_type not in ENTITY_TYPES:
                excluded.append(e.entity_id)
                continue
            type_counts[e.entity_type] += 1
            rr = cls.residual_risk_score(e)
            if rr.get("residual_risk_score") is not None:
                tier_counts[rr["risk_tier"]] += 1
            else:
                excluded.append(e.entity_id)

        return {
            "total_entities": len(entities),
            "by_risk_tier": tier_counts,
            "by_entity_type": type_counts,
            "excluded_count": len(excluded),
            "excluded_sample": excluded[:10],
        }

    # ============================================================================
    # v7.2: L11 RCSA deficiencies → Audit findings feedback loop (CONSUMER)
    # ============================================================================
    @classmethod
    def audit_findings_from_rcsa(
        cls,
        deficiency_classifications: List[Dict[str, Any]],
        target_resolution_days_default: int = 90,
    ) -> Dict[str, Any]:
        """L11 (CONSUMER) — convert RCSA deficiency classifications to
        audit-tracked findings.

        Consumes the per-deficiency dict produced by
        `internal_controls.classify_deficiency()`. Per Charter §7
        Published Language pattern, depends only on the public dict
        contract from internal_controls (severity bands per PCAOB
        AS 2201: deficiency / significant / material).

        Severity → audit treatment:
            material         → CRITICAL finding, 30-day target, audit-committee escalation
            significant      → HIGH finding, 60-day target, management response required
            deficiency       → MEDIUM finding, 90-day target, RCSA owner action

        Returns dict with:
            findings: list[dict] with finding_id, control_id,
                      severity, target_date, status, owner_required,
                      escalation_path
            consumed_payload_version: str — internal_controls schema version
            pattern: str — DDD integration pattern
            cited_invariants: list[str] — none directly (PCAOB framework
                                          is referenced via internal_controls)
            summary: dict — counts by severity
        """
        if not isinstance(deficiency_classifications, list):
            return {
                "status": "INVALID_PAYLOAD",
                "error": "deficiency_classifications must be a list",
                "findings": [],
            }

        SEVERITY_TO_TREATMENT = {
            # Map both raw lowercase and engine's actual uppercase values
            "MATERIAL_WEAKNESS": {
                "audit_severity": "CRITICAL",
                "target_days": 30,
                "escalation": "audit_committee",
                "owner_role": "executive_sponsor_required",
            },
            "SIGNIFICANT_DEFICIENCY": {
                "audit_severity": "HIGH",
                "target_days": 60,
                "escalation": "management_response_required",
                "owner_role": "control_owner_management",
            },
            "DEFICIENCY": {
                "audit_severity": "MEDIUM",
                "target_days": 90,
                "escalation": "rcsa_owner_action",
                "owner_role": "control_owner",
            },
            # Lowercase aliases for backward compatibility / hand-rolled tests
            "material": {
                "audit_severity": "CRITICAL",
                "target_days": 30,
                "escalation": "audit_committee",
                "owner_role": "executive_sponsor_required",
            },
            "significant": {
                "audit_severity": "HIGH",
                "target_days": 60,
                "escalation": "management_response_required",
                "owner_role": "control_owner_management",
            },
            "deficiency": {
                "audit_severity": "MEDIUM",
                "target_days": 90,
                "escalation": "rcsa_owner_action",
                "owner_role": "control_owner",
            },
        }

        findings = []
        invalid_count = 0

        for d in deficiency_classifications:
            if not isinstance(d, dict):
                invalid_count += 1
                continue
            # internal_controls.classify_deficiency returns 'severity'
            severity = d.get("severity") or d.get("classification")
            if severity not in SEVERITY_TO_TREATMENT:
                invalid_count += 1
                continue

            t = SEVERITY_TO_TREATMENT[severity]
            findings.append({
                "finding_id": f"AF-{d.get('deficiency_id', 'UNKNOWN')}",
                "deficiency_id": d.get("deficiency_id"),
                "control_id": d.get("control_id"),
                "rcsa_severity": severity,
                "audit_severity": t["audit_severity"],
                "target_resolution_days": t["target_days"],
                "escalation_path": t["escalation"],
                "owner_role_required": t["owner_role"],
                "status": "OPEN",
                "estimated_financial_impact_kes": d.get("estimated_financial_impact_kes"),
                "affects_financial_reporting": d.get("affects_financial_reporting"),
            })

        # Severity counts for summary
        sev_counts: Dict[str, int] = {}
        for f in findings:
            sev_counts[f["audit_severity"]] = sev_counts.get(f["audit_severity"], 0) + 1

        return {
            "payload_version": "1.0",
            "pattern": "PUBLISHED_LANGUAGE",
            "consumed_payload_version": "internal_controls.classify_deficiency v1.0",
            "cited_invariants": [],
            "findings": findings,
            "summary": {
                "total_findings": len(findings),
                "by_audit_severity": sev_counts,
                "invalid_input_count": invalid_count,
            },
        }


# ============================================================================
# Self-tests
# ============================================================================

def _entity(**kw):
    defaults = dict(
        entity_id="E1", entity_name="Branch Nairobi CBD",
        entity_type="BRANCH",
        financial_materiality_kes=Decimal("60000000"),  # → score 80
        transaction_volume=Decimal("70"),
        regulatory_exposure=Decimal("80"),
        fraud_susceptibility=Decimal("60"),
        process_complexity=Decimal("50"),
        change_velocity=Decimal("40"),
        control_score=Decimal("70"),
    )
    defaults.update(kw)
    return AuditableEntity(**defaults)


def _test_inherent_score_basic():
    r = AuditUniverseEngine.inherent_risk_score(_entity())
    # Weighted: 80×30% + 70×15% + 80×20% + 60×15% + 50×10% + 40×10%
    # = 24 + 10.5 + 16 + 9 + 5 + 4 = 68.5
    assert r["inherent_risk_score"] == "68.50"


def _test_residual_risk_with_control():
    r = AuditUniverseEngine.residual_risk_score(_entity())
    # Inherent 68.5 × (1 - 70/100) = 68.5 × 0.30 = 20.55 → LOW
    assert r["risk_tier"] == "LOW"
    assert r["residual_risk_score"] == "20.55"


def _test_residual_risk_no_control_assumes_worst():
    e = _entity(control_score=None)
    r = AuditUniverseEngine.residual_risk_score(e)
    # No control → residual = inherent = 68.5 → MEDIUM
    assert r["risk_tier"] == "MEDIUM"
    assert r["control_basis"] == "no_control_data_assumed_no_mitigation"


def _test_high_risk_classification():
    e = _entity(
        financial_materiality_kes=Decimal("200000000"),  # → 100
        transaction_volume=Decimal("100"),
        regulatory_exposure=Decimal("100"),
        fraud_susceptibility=Decimal("100"),
        process_complexity=Decimal("100"),
        change_velocity=Decimal("100"),
        control_score=Decimal("10"),  # poor controls
    )
    r = AuditUniverseEngine.residual_risk_score(e)
    # Inherent = 100; residual = 100 × 0.9 = 90 → HIGH
    assert r["risk_tier"] == "HIGH"
    assert r["audit_frequency_months"] == 12


def _test_inherent_score_missing_factors_rule6():
    e = _entity(transaction_volume=None, fraud_susceptibility=None)
    r = AuditUniverseEngine.inherent_risk_score(e)
    # Should still compute score with re-normalised weights
    assert r["inherent_risk_score"] is not None
    assert "transaction_volume" in r["missing_factors"]
    assert r["factor_count_used"] == 4


def _test_inherent_all_missing_rule6():
    e = AuditableEntity(entity_id="E1", entity_name="X", entity_type="BRANCH")
    r = AuditUniverseEngine.inherent_risk_score(e)
    assert r["inherent_risk_score"] is None


def _test_residual_no_inherent_rule1():
    e = AuditableEntity(entity_id="E1", entity_name="X", entity_type="BRANCH")
    r = AuditUniverseEngine.residual_risk_score(e)
    assert r["residual_risk_score"] is None


def _test_control_rating_effective():
    r = AuditUniverseEngine.control_environment_score(Decimal("95"))
    assert r["control_rating"] == "EFFECTIVE"


def _test_control_rating_ineffective():
    r = AuditUniverseEngine.control_environment_score(Decimal("30"))
    assert r["control_rating"] == "INEFFECTIVE"


def _test_control_rating_out_of_range():
    r = AuditUniverseEngine.control_environment_score(Decimal("150"))
    assert "error" in r


def _test_audit_plan_high_risk_annual():
    e = _entity(
        financial_materiality_kes=Decimal("200000000"),
        transaction_volume=Decimal("100"),
        regulatory_exposure=Decimal("100"),
        fraud_susceptibility=Decimal("100"),
        process_complexity=Decimal("100"),
        change_velocity=Decimal("100"),
        control_score=Decimal("0"),
    )
    plan = AuditUniverseEngine.generate_audit_plan(
        [e], plan_start=date(2026, 1, 1), plan_horizon_years=3
    )
    # HIGH = annual = 3 audits in 3 years
    audits_for_e = [a for a in plan["scheduled_audits"] if a["entity_id"] == e.entity_id]
    assert len(audits_for_e) == 3


def _test_audit_plan_low_risk_triennial():
    e = _entity(control_score=Decimal("95"))  # very effective controls
    plan = AuditUniverseEngine.generate_audit_plan(
        [e], plan_start=date(2026, 1, 1), plan_horizon_years=3
    )
    # LOW = triennial = 1 audit in 3 years
    audits_for_e = [a for a in plan["scheduled_audits"] if a["entity_id"] == e.entity_id]
    assert len(audits_for_e) == 1


def _test_audit_universe_summary():
    entities = [_entity(entity_id=f"E{i}") for i in range(5)]
    r = AuditUniverseEngine.audit_universe_summary(entities)
    assert r["total_entities"] == 5
    assert r["by_entity_type"]["BRANCH"] == 5


def _test_risk_tier_thresholds_byte_for_byte():
    assert HIGH_RISK_THRESHOLD == Decimal("70")
    assert MEDIUM_RISK_THRESHOLD == Decimal("40")


def _test_audit_frequency_byte_for_byte():
    assert AUDIT_FREQUENCY_MONTHS["HIGH"] == 12
    assert AUDIT_FREQUENCY_MONTHS["MEDIUM"] == 24
    assert AUDIT_FREQUENCY_MONTHS["LOW"] == 36


def _test_inherent_weights_sum_to_100():
    total = sum(INHERENT_RISK_WEIGHTS_PCT.values())
    assert total == Decimal("100")


def _test_inherent_weights_byte_for_byte():
    assert INHERENT_RISK_WEIGHTS_PCT["financial_materiality_kes"] == Decimal("30")
    assert INHERENT_RISK_WEIGHTS_PCT["transaction_volume"] == Decimal("15")
    assert INHERENT_RISK_WEIGHTS_PCT["regulatory_exposure"] == Decimal("20")
    assert INHERENT_RISK_WEIGHTS_PCT["fraud_susceptibility"] == Decimal("15")
    assert INHERENT_RISK_WEIGHTS_PCT["process_complexity"] == Decimal("10")
    assert INHERENT_RISK_WEIGHTS_PCT["change_velocity"] == Decimal("10")


def _test_control_rating_bands_byte_for_byte():
    assert CONTROL_RATING_BANDS["EFFECTIVE"] == (Decimal("90"), Decimal("100"))
    assert CONTROL_RATING_BANDS["LARGELY_EFFECTIVE"] == (Decimal("70"), Decimal("89"))
    assert CONTROL_RATING_BANDS["PARTIALLY_EFFECTIVE"] == (Decimal("50"), Decimal("69"))
    assert CONTROL_RATING_BANDS["INEFFECTIVE"] == (Decimal("25"), Decimal("49"))
    assert CONTROL_RATING_BANDS["NON_EXISTENT"] == (Decimal("0"), Decimal("24"))


def self_test() -> bool:
    tests = [
        _test_inherent_score_basic,
        _test_residual_risk_with_control,
        _test_residual_risk_no_control_assumes_worst,
        _test_high_risk_classification,
        _test_inherent_score_missing_factors_rule6,
        _test_inherent_all_missing_rule6,
        _test_residual_no_inherent_rule1,
        _test_control_rating_effective,
        _test_control_rating_ineffective,
        _test_control_rating_out_of_range,
        _test_audit_plan_high_risk_annual,
        _test_audit_plan_low_risk_triennial,
        _test_audit_universe_summary,
        _test_risk_tier_thresholds_byte_for_byte,
        _test_audit_frequency_byte_for_byte,
        _test_inherent_weights_sum_to_100,
        _test_inherent_weights_byte_for_byte,
        _test_control_rating_bands_byte_for_byte,
    ]
    print("=" * 60)
    print("Audit Universe Engine — Self-Tests (#81)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)
