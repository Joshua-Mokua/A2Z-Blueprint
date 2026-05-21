"""composite_scores.py — caller-side composition layer for multi-engine summaries.

v6.0 introduces this thin utility module as the **composite scoring layer**
for engines that produce multiple independent outputs but lack a single
unified "health score". This is NOT a new standard — it's pure-Python
composition over existing engine outputs.

**Philosophy**: existing engines produce rich multi-dimensional outputs
(e.g. compensation produces gender_pay_gap + ceo_ratio + internal_equity
+ pay_distribution; engagement produces engagement_score + enps +
drivers_breakdown + sentiment + flight_risk). Each individual output is
useful, but board reporting often needs a single number. Rather than
modifying engines (which would proliferate composition bias into every
engine), v6.0 keeps engines deterministic and unbiased while providing
this thin composition layer.

**Composite semantics**:
- All composites return a dict with: score (0-100), severity, components
  (per-input contribution), reason (Rule 6 if any inputs missing).
- Weights are exposed as constants — caller can override per market or
  bank policy.
- Missing inputs surface in `missing_inputs` list (Rule 6 transparency).
- All functions are pure (no side effects, no I/O).

**Coverage in v6.0**:
- workforce_health_composite — engagement + compensation domains
- customer_value_composite — RFM + CLV + Customer Value segments
- rcsa_health_composite — COSO + control effectiveness + deficiency

Future composites can follow the same pattern.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────
# Default weights — exposed for caller override
# ──────────────────────────────────────────────────────────────────────

# Workforce health weights — engagement_score (0.40) dominates as the
# single best individual signal; eNPS (0.25) is forward-looking; weakest
# driver (0.20) surfaces concentration risk; inverse flight risk (0.15)
# accounts for retention quality.
WORKFORCE_HEALTH_WEIGHTS = {
    "engagement_score": Decimal("0.40"),
    "enps_normalised": Decimal("0.25"),
    "weakest_driver": Decimal("0.20"),
    "inverse_flight_risk": Decimal("0.15"),
}

# Customer value composite — values reflect typical retail bank emphasis.
# RFM (0.30) is the most actionable behavioral signal; CLV (0.40) is the
# best long-term value proxy; Customer Value tier (0.30) captures
# banking-archetype + retention robustness.
CUSTOMER_VALUE_COMPOSITE_WEIGHTS = {
    "rfm_segment_score": Decimal("0.30"),
    "clv_normalised": Decimal("0.40"),
    "customer_value_tier_score": Decimal("0.30"),
}

# RCSA health weights — COSO score (0.40) is foundational; control
# effectiveness (0.35) is the operational measure; deficiency severity
# (0.25) captures known weaknesses.
RCSA_HEALTH_WEIGHTS = {
    "coso_overall_normalised": Decimal("0.40"),
    "control_effectiveness_pct": Decimal("0.35"),
    "deficiency_severity_inverse": Decimal("0.25"),
}

# AML health weights (v7.5) — KYC band stability (0.30) is foundational
# (more LOW-risk customers = healthier book); alert disposition (0.30)
# measures how effectively the bank closes investigations; SAR conversion
# rate (0.20) gauges true-positive precision; transaction velocity stability
# (0.20) flags emerging suspicious-pattern shifts.
AML_HEALTH_WEIGHTS = {
    "kyc_band_stability_pct": Decimal("0.30"),       # % LOW + MEDIUM bands (stable)
    "alert_disposition_pct": Decimal("0.30"),         # % alerts moved out of OPEN
    "sar_conversion_pct_inverse": Decimal("0.20"),    # inverse — too high = noise; too low = missed
    "txn_velocity_stability_pct": Decimal("0.20"),    # period-over-period stability
}

# Severity bands — used by all composites
COMPOSITE_HEALTHY_THRESHOLD = Decimal("75")
COMPOSITE_MODERATE_THRESHOLD = Decimal("60")


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _severity(score: Optional[Decimal]) -> str:
    """Map composite score to severity band."""
    if score is None:
        return "UNKNOWN"
    if score >= COMPOSITE_HEALTHY_THRESHOLD:
        return "HEALTHY"
    if score >= COMPOSITE_MODERATE_THRESHOLD:
        return "MODERATE"
    return "LOW"


def _safe_decimal(v: Any) -> Optional[Decimal]:
    """Coerce to Decimal or None — handles strings, floats, missing values."""
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _clip(v: Decimal, lo: Decimal = Decimal("0"),
          hi: Decimal = Decimal("100")) -> Decimal:
    """Clip value to [lo, hi]."""
    return max(lo, min(hi, v))


# ──────────────────────────────────────────────────────────────────────
# Workforce Health Composite (v6.0)
# ──────────────────────────────────────────────────────────────────────

def workforce_health_composite(
    engagement_score: Optional[float] = None,
    enps: Optional[float] = None,
    weakest_driver_score: Optional[float] = None,
    flight_risk_high_pct: Optional[float] = None,
    weights: Optional[Dict[str, Decimal]] = None,
) -> Dict[str, Any]:
    """Compose 4 engagement signals into a unified workforce health score.

    Inputs (all 0-100 except enps which is -100 to 100):
    - engagement_score: from EmployeeEngagementEngine.engagement_score
    - enps: from EmployeeEngagementEngine.enps (normalised internally
      from -100..100 to 0..100)
    - weakest_driver_score: min driver score from drivers_breakdown
    - flight_risk_high_pct: percentage of staff at HIGH flight risk
      (inverted internally — high flight risk → low health contribution)

    Returns dict with:
    - score: composite 0-100 (None if all inputs missing)
    - severity: HEALTHY / MODERATE / LOW / UNKNOWN
    - components: per-input contributions (after weight)
    - missing_inputs: list of input names not provided (Rule 6)
    - weights_used: weights snapshot for audit trail
    """
    w = weights or WORKFORCE_HEALTH_WEIGHTS
    components: Dict[str, Optional[Decimal]] = {}
    missing: List[str] = []

    eng = _safe_decimal(engagement_score)
    if eng is None:
        missing.append("engagement_score")
    else:
        components["engagement_score"] = _clip(eng) * w["engagement_score"]

    enps_d = _safe_decimal(enps)
    if enps_d is None:
        missing.append("enps")
    else:
        # Map -100..100 to 0..100
        enps_normalised = _clip((enps_d + Decimal("100")) / Decimal("2"))
        components["enps_normalised"] = enps_normalised * w["enps_normalised"]

    weakest = _safe_decimal(weakest_driver_score)
    if weakest is None:
        missing.append("weakest_driver_score")
    else:
        components["weakest_driver"] = _clip(weakest) * w["weakest_driver"]

    fr_pct = _safe_decimal(flight_risk_high_pct)
    if fr_pct is None:
        missing.append("flight_risk_high_pct")
    else:
        # Invert: 0% flight risk → 100, 100% flight risk → 0
        inverse = _clip(Decimal("100") - fr_pct)
        components["inverse_flight_risk"] = inverse * w["inverse_flight_risk"]

    # Compute weighted score from available components
    if not components:
        return {
            "score": None,
            "severity": "UNKNOWN",
            "components": {},
            "missing_inputs": missing,
            "weights_used": {k: str(v) for k, v in w.items()},
            "reason": "all_inputs_missing",
        }

    # If some inputs missing, renormalise weights over available
    available_weight = sum(w[k_to_w] for k_to_w in
        [_component_to_weight_key(c) for c in components.keys()])
    raw_sum = sum(components.values())
    score = (raw_sum / available_weight) if available_weight > 0 else None

    return {
        "score": float(score) if score is not None else None,
        "severity": _severity(score),
        "components": {k: float(v) for k, v in components.items()},
        "missing_inputs": missing,
        "weights_used": {k: str(v) for k, v in w.items()},
        "reason": "computed" if not missing else "computed_with_missing",
    }


def _component_to_weight_key(component_key: str) -> str:
    """Map component output key back to weight dict key."""
    # Identity for most, but engagement_score → engagement_score (no change)
    return component_key


# ──────────────────────────────────────────────────────────────────────
# Customer Value Composite (v6.0)
# ──────────────────────────────────────────────────────────────────────

# RFM segments mapped to numeric scores (0-100)
RFM_SEGMENT_SCORES = {
    "CHAMPIONS": 100,
    "LOYAL_CUSTOMERS": 90,
    "POTENTIAL_LOYALISTS": 80,
    "RECENT_CUSTOMERS": 70,
    "PROMISING": 65,
    "NEED_ATTENTION": 50,
    "ABOUT_TO_SLEEP": 40,
    "AT_RISK": 30,
    "CANNOT_LOSE_THEM": 35,  # high value but at risk
    "HIBERNATING": 20,
    "LOST": 10,
}

# Customer Value tier scores
CUSTOMER_VALUE_TIER_SCORES = {
    "PLATINUM": 100,
    "GOLD": 75,
    "SILVER": 50,
    "BRONZE": 25,
}

# CLV normalisation reference points (in KES)
CLV_NORMALISATION_HIGH = Decimal("1000000")  # 1M KES → 100
CLV_NORMALISATION_LOW = Decimal("0")          # 0 KES → 0


def customer_value_composite(
    rfm_segment: Optional[str] = None,
    clv_kes: Optional[float] = None,
    customer_value_tier: Optional[str] = None,
    weights: Optional[Dict[str, Decimal]] = None,
) -> Dict[str, Any]:
    """Compose 3 segmentation lenses into a unified customer value score.

    Inputs:
    - rfm_segment: from CustomerSegmentationEngine.rfm_segment (string label)
    - clv_kes: from CustomerLifetimeValueEngine.clv_npv (KES amount)
    - customer_value_tier: from CustomerValueEngine.segment_classification
      (PLATINUM/GOLD/SILVER/BRONZE)

    Returns dict with same shape as workforce_health_composite.
    """
    w = weights or CUSTOMER_VALUE_COMPOSITE_WEIGHTS
    components: Dict[str, Decimal] = {}
    missing: List[str] = []

    if rfm_segment is None:
        missing.append("rfm_segment")
    elif rfm_segment in RFM_SEGMENT_SCORES:
        components["rfm_segment_score"] = (
            Decimal(RFM_SEGMENT_SCORES[rfm_segment]) * w["rfm_segment_score"])
    else:
        missing.append("rfm_segment")

    clv = _safe_decimal(clv_kes)
    if clv is None:
        missing.append("clv_kes")
    else:
        # Normalise CLV to 0-100 scale
        if clv <= CLV_NORMALISATION_LOW:
            clv_norm = Decimal("0")
        elif clv >= CLV_NORMALISATION_HIGH:
            clv_norm = Decimal("100")
        else:
            clv_norm = (clv / CLV_NORMALISATION_HIGH) * Decimal("100")
        components["clv_normalised"] = clv_norm * w["clv_normalised"]

    if customer_value_tier is None:
        missing.append("customer_value_tier")
    elif customer_value_tier in CUSTOMER_VALUE_TIER_SCORES:
        components["customer_value_tier_score"] = (
            Decimal(CUSTOMER_VALUE_TIER_SCORES[customer_value_tier])
            * w["customer_value_tier_score"])
    else:
        missing.append("customer_value_tier")

    if not components:
        return {
            "score": None,
            "severity": "UNKNOWN",
            "components": {},
            "missing_inputs": missing,
            "weights_used": {k: str(v) for k, v in w.items()},
            "reason": "all_inputs_missing",
        }

    available_weight = sum(w[_component_to_weight_key(c)]
                            for c in components.keys())
    raw_sum = sum(components.values())
    score = (raw_sum / available_weight) if available_weight > 0 else None

    return {
        "score": float(score) if score is not None else None,
        "severity": _severity(score),
        "components": {k: float(v) for k, v in components.items()},
        "missing_inputs": missing,
        "weights_used": {k: str(v) for k, v in w.items()},
        "reason": "computed" if not missing else "computed_with_missing",
    }


# ──────────────────────────────────────────────────────────────────────
# RCSA Health Composite (v6.0)
# ──────────────────────────────────────────────────────────────────────

def rcsa_health_composite(
    coso_overall_score: Optional[float] = None,
    control_effectiveness_pct: Optional[float] = None,
    material_weakness_count: Optional[int] = None,
    significant_deficiency_count: Optional[int] = None,
    deficiency_count: Optional[int] = None,
    weights: Optional[Dict[str, Decimal]] = None,
) -> Dict[str, Any]:
    """Compose RCSA signals into unified internal controls health score.

    Inputs:
    - coso_overall_score: from coso_component_score (1-5 likert,
      normalised to 0-100 internally as score * 20)
    - control_effectiveness_pct: from control_effectiveness_summary (0-100)
    - material_weakness_count + significant_deficiency_count +
      deficiency_count: counts from classify_deficiency aggregation;
      converted to inverse severity score (more weakness → lower score)

    Returns dict with same shape as workforce_health_composite.
    """
    w = weights or RCSA_HEALTH_WEIGHTS
    components: Dict[str, Decimal] = {}
    missing: List[str] = []

    coso = _safe_decimal(coso_overall_score)
    if coso is None:
        missing.append("coso_overall_score")
    else:
        # Map 1-5 likert to 0-100
        coso_norm = _clip((coso - Decimal("1")) / Decimal("4")
                            * Decimal("100"))
        components["coso_overall_normalised"] = (coso_norm
            * w["coso_overall_normalised"])

    eff = _safe_decimal(control_effectiveness_pct)
    if eff is None:
        missing.append("control_effectiveness_pct")
    else:
        components["control_effectiveness_pct"] = (_clip(eff)
            * w["control_effectiveness_pct"])

    # Deficiency severity inverse: penalize material weakness heavily,
    # significant moderately, ordinary lightly
    if (material_weakness_count is None
            and significant_deficiency_count is None
            and deficiency_count is None):
        missing.append("deficiency_counts")
    else:
        material = int(material_weakness_count or 0)
        significant = int(significant_deficiency_count or 0)
        ordinary = int(deficiency_count or 0)
        # Penalty: each material -25, each significant -10, each ordinary -3
        penalty = (Decimal(material) * Decimal("25")
                    + Decimal(significant) * Decimal("10")
                    + Decimal(ordinary) * Decimal("3"))
        deficiency_inverse = _clip(Decimal("100") - penalty)
        components["deficiency_severity_inverse"] = (deficiency_inverse
            * w["deficiency_severity_inverse"])

    if not components:
        return {
            "score": None,
            "severity": "UNKNOWN",
            "components": {},
            "missing_inputs": missing,
            "weights_used": {k: str(v) for k, v in w.items()},
            "reason": "all_inputs_missing",
        }

    available_weight = sum(w[_component_to_weight_key(c)]
                            for c in components.keys())
    raw_sum = sum(components.values())
    score = (raw_sum / available_weight) if available_weight > 0 else None

    return {
        "score": float(score) if score is not None else None,
        "severity": _severity(score),
        "components": {k: float(v) for k, v in components.items()},
        "missing_inputs": missing,
        "weights_used": {k: str(v) for k, v in w.items()},
        "reason": "computed" if not missing else "computed_with_missing",
    }


# ──────────────────────────────────────────────────────────────────────
# AML health composite (v7.5)
# ──────────────────────────────────────────────────────────────────────

def aml_health_composite(
    kyc_band_distribution: Optional[Dict[str, int]] = None,
    alert_summary: Optional[Dict[str, Any]] = None,
    sar_conversion_pct: Optional[float] = None,
    txn_velocity_change_pct: Optional[float] = None,
    weights: Optional[Dict[str, Decimal]] = None,
) -> Dict[str, Any]:
    """AML-health composite (v7.5) — single 0-100 score for AML programme health.

    Composes 4 inputs into a single AML-health score:

    1. KYC band stability — % of customers in LOW + MEDIUM bands. A book
       skewed toward HIGH/PROHIBITED is risk-concentrated.
       Pass `kyc_band_distribution = {"LOW": 525000, "MEDIUM": 140000,
                                       "HIGH": 35000, "PROHIBITED": 0}`
       (matches `system_stocks.customer_base.by_kyc_risk_band_count`).

    2. Alert disposition — % of alerts that have moved out of OPEN status
       (into INVESTIGATING / SAR_FILED / DISMISSED). Pass `alert_summary`
       from `transaction_monitoring.alert_summary()`.

    3. SAR conversion rate — % of dispositioned alerts that became SARs.
       Inverse-scored: 5-15% is healthy (right-sized investigation); below
       1% suggests over-alerting (noise); above 25% suggests under-alerting
       (missed detections). The score peaks at 10% and falls off either side.

    4. Transaction velocity stability — period-over-period change in mean
       txn velocity. Stable (±10%) = healthy; volatile = potential
       suspicious pattern shifts.

    Per Charter §13: this is a Customer Intelligence + Compliance/AML
    composite. Composes outputs from kyc_aml_risk + transaction_monitoring
    using Published Language pattern.

    Returns standard composite-scores dict:
        score (0-100), severity (HEALTHY/MODERATE/AT_RISK), components,
        missing_inputs, weights_used, reason.
    """
    w = weights or AML_HEALTH_WEIGHTS

    components: Dict[str, Decimal] = {}
    missing: List[str] = []

    # 1. KYC band stability
    if kyc_band_distribution and isinstance(kyc_band_distribution, dict):
        total = sum(kyc_band_distribution.values()) if kyc_band_distribution else 0
        if total > 0:
            stable_count = (kyc_band_distribution.get("LOW", 0) +
                            kyc_band_distribution.get("MEDIUM", 0))
            stability_pct = Decimal(str(stable_count / total * 100))
            components["kyc_band_stability_pct"] = _clip(
                stability_pct, Decimal("0"), Decimal("100"))
        else:
            missing.append("kyc_band_distribution_empty")
    else:
        missing.append("kyc_band_distribution")

    # 2. Alert disposition
    if alert_summary and isinstance(alert_summary, dict):
        total_alerts = alert_summary.get("total_alerts", 0)
        by_status = alert_summary.get("by_status", {})
        open_count = by_status.get("OPEN", 0) + by_status.get("INVESTIGATING", 0)
        if total_alerts > 0:
            dispositioned_count = total_alerts - open_count
            disposition_pct = Decimal(str(dispositioned_count / total_alerts * 100))
            components["alert_disposition_pct"] = _clip(
                disposition_pct, Decimal("0"), Decimal("100"))
        elif total_alerts == 0:
            # No alerts at all — treat as healthy on this axis
            components["alert_disposition_pct"] = Decimal("100")
        else:
            missing.append("alert_summary_invalid")
    else:
        missing.append("alert_summary")

    # 3. SAR conversion rate (inverse-scored — peaks at 10%)
    sar_pct_d = _safe_decimal(sar_conversion_pct)
    if sar_pct_d is not None:
        # Healthy band: 5-15%, peak at 10%. Score = 100 - 5*|pct - 10| clipped 0-100.
        distance_from_ideal = abs(sar_pct_d - Decimal("10"))
        sar_score = Decimal("100") - distance_from_ideal * Decimal("5")
        components["sar_conversion_pct_inverse"] = _clip(
            sar_score, Decimal("0"), Decimal("100"))
    else:
        missing.append("sar_conversion_pct")

    # 4. Transaction velocity stability
    velocity_d = _safe_decimal(txn_velocity_change_pct)
    if velocity_d is not None:
        # Stable: ±10%. Score = 100 - 5*|change| clipped 0-100.
        absolute_change = abs(velocity_d)
        stability_score = Decimal("100") - absolute_change * Decimal("5")
        components["txn_velocity_stability_pct"] = _clip(
            stability_score, Decimal("0"), Decimal("100"))
    else:
        missing.append("txn_velocity_change_pct")

    if not components:
        return {
            "score": None,
            "severity": "UNKNOWN",
            "components": {},
            "missing_inputs": missing,
            "weights_used": {k: str(v) for k, v in w.items()},
            "reason": "all_inputs_missing",
        }

    available_weight = sum(w[c] for c in components.keys() if c in w)
    raw_sum = sum(components[c] * w[c] for c in components.keys() if c in w)
    score = (raw_sum / available_weight) if available_weight > 0 else None

    return {
        "score": float(score) if score is not None else None,
        "severity": _severity(score),
        "components": {k: float(v) for k, v in components.items()},
        "missing_inputs": missing,
        "weights_used": {k: str(v) for k, v in w.items()},
        "reason": "computed" if not missing else "computed_with_missing",
    }


# ──────────────────────────────────────────────────────────────────────
# All composites — convenience batch
# ──────────────────────────────────────────────────────────────────────

ALL_COMPOSITES = {
    "workforce_health": workforce_health_composite,
    "customer_value": customer_value_composite,
    "rcsa_health": rcsa_health_composite,
    "aml_health": aml_health_composite,
}
