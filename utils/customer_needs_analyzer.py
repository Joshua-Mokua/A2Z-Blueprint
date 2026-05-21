"""utils.customer_needs_analyzer — Customer Needs & Gap Analysis
(Standard ENH-133, v10.144). Phase 1E Product Module — third engine.

Per Continuation.docx §Standard #133 (Eco Bank QA spec):
    Customer needs registry, gap analysis, and value proposition
    builder.

NOTE — scope split with ENH-135
    "Value proposition builder" mentioned in the spec is the scope
    of ENH-135 CVP Builder (next-but-one drop). ENH-133 ships the
    needs registry foundation + gap analysis layer. ENH-135 will
    consume this engine's outputs to generate per-segment value
    propositions.

This is the THIRD of ten Phase 1E Product standards (ENH-131..140,
closing at ~v10.146 with cockpit + API + UI gate per the v10.141
standing norm).

Per Rule 7 (No silent ML predictions):
  1. Gap detection is fully deterministic — same input → same gaps
  2. Need priorities and segment expectations are NAMED registry
     entries (data/customer_needs_registry.json); banks override
  3. Behavioural-signal gaps trigger on EXPLICIT thresholds
     (e.g. churn_risk > 0.5) — never on opaque ML predictions
  4. Honest fallback when customer_intelligence.json doesn't have
     the customer — returns explicit fallback_reason rather than
     fabricating a segment

WHAT THIS MODULE SHIPS
----------------------
1. CustomerNeedsAnalyzer class with:
   - get_customer_needs(customer_id) — needs ranked by priority
     using propensity_scores order + segment defaults
   - analyze_customer_gap(customer_id) — full gap analysis combining
     portfolio-count gap + behavioural-signal gaps
   - get_segment_gap_summary(segment) — aggregate over a segment
   - get_top_unmet_needs(top_n=10) — bank-wide ranking by frequency
     × CLV impact
   - get_high_priority_gaps(min_clv=None) — high-value at-risk
     customers
   - bank_wide_gap_summary() — totals + ratios

2. Reads:
   - data/customer_needs_registry.json (NEW v10.144 seed; needs
     catalogue + segment_expectations)
   - data/customer_intelligence.json (3000 customer records with
     segment, products_held, propensity_scores, churn_risk,
     digital_engagement, last_contact_days, complaints_12m,
     clv_estimate)
   - data/products.json (product portfolio reference)

HONESTY DISCIPLINE
------------------
- Per-customer gap analysis NEVER fabricates per-product holdings
  (customer_intelligence.json holds an integer count, not a list).
  The engine is honest about what it sees: portfolio-count gaps
  vs segment expectation; propensity-based unmet needs (next-best
  product not yet held); behavioural-signal gaps (churn risk,
  service quality, contact cadence, digital activation).
- HIGH/MEDIUM/LOW gap severity uses explicit threshold rules with
  the rule chain logged in the result's `severity_rationale`.
- Aggregations report n_customers_evaluated explicitly; if the
  segment is empty in customer_intelligence.json, the engine
  returns ok=False with fallback_reason.

RELATED STANDARDS
-----------------
- ENH-134 Competitive Intelligence (next drop) — provides the
  competitive context for gap-driven product recommendations.
- ENH-135 CVP Builder — consumes this engine's outputs to draft
  per-segment value propositions.
- ENH-138 AI Product Recommendation — will use ranked unmet
  propensities as candidate set.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA_DIR = Path(__file__).parent.parent / "data"
NEEDS_REGISTRY_PATH = DATA_DIR / "customer_needs_registry.json"
CUSTOMER_INTEL_PATH = DATA_DIR / "customer_intelligence.json"
PRODUCTS_PATH = DATA_DIR / "products.json"


@dataclass(frozen=True)
class CustomerGap:
    customer_id: str
    segment: Optional[str]
    products_held: int
    expected_products: int
    portfolio_gap_count: int          # max(expected - held, 0)
    propensity_gaps: Tuple[str, ...]   # ranked unmet propensities
    behavioural_gaps: Tuple[Dict[str, Any], ...]   # signal-triggered
    overall_severity: str              # HIGH | MEDIUM | LOW | NONE
    severity_rationale: Tuple[str, ...]
    clv_estimate_kes: Optional[Decimal]
    found: bool
    fallback_reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "segment": self.segment,
            "products_held": self.products_held,
            "expected_products": self.expected_products,
            "portfolio_gap_count": self.portfolio_gap_count,
            "propensity_gaps": list(self.propensity_gaps),
            "behavioural_gaps": list(self.behavioural_gaps),
            "overall_severity": self.overall_severity,
            "severity_rationale": list(self.severity_rationale),
            "clv_estimate_kes": (str(self.clv_estimate_kes)
                                  if self.clv_estimate_kes is not None
                                  else None),
            "found": self.found,
            "fallback_reason": self.fallback_reason,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CustomerNeedsAnalyzer:
    """Customer needs catalogue + gap analysis from the registry +
    customer_intelligence.json + products.json.

    Read-only contract — never writes.
    """

    HIGH_SEVERITY_PORTFOLIO_GAP = 3   # expected - held >= 3 → HIGH
    MEDIUM_SEVERITY_PORTFOLIO_GAP = 1
    HIGH_SEVERITY_BEHAVIOURAL_COUNT = 2  # 2+ behavioural gaps → HIGH

    def __init__(
        self,
        needs_registry_path: Optional[Path] = None,
        customer_intel_path: Optional[Path] = None,
        products_path: Optional[Path] = None,
    ) -> None:
        self.needs_registry_path = needs_registry_path or NEEDS_REGISTRY_PATH
        self.customer_intel_path = customer_intel_path or CUSTOMER_INTEL_PATH
        self.products_path = products_path or PRODUCTS_PATH
        self._registry_cache: Optional[Dict[str, Any]] = None
        self._intel_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_registry(self) -> Dict[str, Any]:
        if self._registry_cache is None:
            try:
                with open(self.needs_registry_path) as f:
                    self._registry_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self._registry_cache = {"needs": [],
                                          "segment_expectations": {}}
        return self._registry_cache

    def _load_intel(self) -> Dict[str, Any]:
        if self._intel_cache is None:
            try:
                with open(self.customer_intel_path) as f:
                    self._intel_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self._intel_cache = {}
        return self._intel_cache or {}

    # ------------------------------------------------------------------
    # Customer needs — ranked
    # ------------------------------------------------------------------

    def get_customer_needs(self, customer_id: str) -> Dict[str, Any]:
        intel = self._load_intel().get(str(customer_id))
        if not intel:
            return {"customer_id": customer_id, "ok": False,
                    "fallback_reason": "customer_not_found",
                    "needs": []}

        registry = self._load_registry()
        segment = intel.get("segment")
        propensities: List[str] = list(intel.get("propensity_scores", []))

        # Build ranked needs list:
        #  1. Propensity-driven (in order from customer's own ranking)
        #  2. Need-registry items applicable to this segment that
        #     aren't already represented by a propensity
        ranked_needs: List[Dict[str, Any]] = []
        seen_need_ids: set = set()

        # 1. Propensity-driven (the customer's own next-best ladder)
        for prop in propensities:
            ranked_needs.append({
                "need_id": f"PROPENSITY:{prop}",
                "source": "propensity_scores",
                "rank_basis": "customer_revealed_preference",
                "priority": "HIGH",
                "description": f"Acquire: {prop}",
            })

        # 2. Registry needs applicable to this segment
        for need in registry.get("needs", []):
            if segment in need.get("applicable_segments", []):
                if need["need_id"] not in seen_need_ids:
                    ranked_needs.append({
                        "need_id": need["need_id"],
                        "source": "needs_registry",
                        "rank_basis": "segment_archetype_priority",
                        "priority": need.get("priority", "MEDIUM"),
                        "description": need.get("description", ""),
                    })
                    seen_need_ids.add(need["need_id"])

        return {
            "customer_id": customer_id,
            "ok": True,
            "segment": segment,
            "n_needs": len(ranked_needs),
            "needs": ranked_needs,
        }

    # ------------------------------------------------------------------
    # Per-customer gap analysis
    # ------------------------------------------------------------------

    def analyze_customer_gap(self, customer_id: str) -> CustomerGap:
        intel = self._load_intel().get(str(customer_id))
        if not intel:
            return CustomerGap(
                customer_id=customer_id, segment=None,
                products_held=0, expected_products=0,
                portfolio_gap_count=0, propensity_gaps=(),
                behavioural_gaps=(), overall_severity="NONE",
                severity_rationale=("customer_not_found",),
                clv_estimate_kes=None, found=False,
                fallback_reason="customer_not_found")

        segment = intel.get("segment")
        registry = self._load_registry()
        seg_exp = registry.get("segment_expectations", {}).get(segment, {})

        products_held = int(intel.get("products_held", 0) or 0)
        expected = int(seg_exp.get("expected_products_held", 0) or 0)
        portfolio_gap = max(expected - products_held, 0)

        # Propensity gaps — propensity_scores list represents the
        # customer's ranked unmet needs already (each entry is a product
        # the customer is propensity-scored to acquire = doesn't yet hold)
        propensities = tuple(intel.get("propensity_scores", []))

        # Behavioural gaps
        behavioural_gaps: List[Dict[str, Any]] = []
        churn = float(intel.get("churn_risk", 0) or 0)
        max_churn = float(seg_exp.get("max_acceptable_churn_risk", 1.0))
        if churn > max_churn:
            behavioural_gaps.append({
                "need_id": "RETENTION_RISK_MITIGATION",
                "actual": churn, "threshold": max_churn,
                "severity": "HIGH" if churn > 0.6 else "MEDIUM",
            })

        complaints = int(intel.get("complaints_12m", 0) or 0)
        max_complaints = int(seg_exp.get(
            "max_acceptable_complaints_12m", 999))
        if complaints > max_complaints:
            behavioural_gaps.append({
                "need_id": "SERVICE_QUALITY_RECOVERY",
                "actual": complaints, "threshold": max_complaints,
                "severity": "HIGH" if complaints >= 3 else "MEDIUM",
            })

        last_contact = int(intel.get("last_contact_days", 0) or 0)
        max_lc = int(seg_exp.get("max_acceptable_last_contact_days", 999))
        if last_contact > max_lc:
            behavioural_gaps.append({
                "need_id": "RELATIONSHIP_MANAGEMENT",
                "actual": last_contact, "threshold": max_lc,
                "severity": ("HIGH" if last_contact > max_lc * 2
                              else "MEDIUM"),
            })

        digital = str(intel.get("digital_engagement", "") or "")
        if digital == "Low":
            behavioural_gaps.append({
                "need_id": "DIGITAL_CONVENIENCE",
                "actual": digital, "threshold": "Medium+",
                "severity": "MEDIUM",
            })

        # Overall severity
        rationale: List[str] = []
        severity = "NONE"
        if portfolio_gap >= self.HIGH_SEVERITY_PORTFOLIO_GAP:
            severity = "HIGH"
            rationale.append(
                f"portfolio_gap_count={portfolio_gap}>="
                f"{self.HIGH_SEVERITY_PORTFOLIO_GAP}_threshold")
        elif portfolio_gap >= self.MEDIUM_SEVERITY_PORTFOLIO_GAP:
            severity = "MEDIUM"
            rationale.append(
                f"portfolio_gap_count={portfolio_gap}>="
                f"{self.MEDIUM_SEVERITY_PORTFOLIO_GAP}_threshold")

        n_high_beh = sum(1 for g in behavioural_gaps
                          if g.get("severity") == "HIGH")
        n_total_beh = len(behavioural_gaps)
        if n_high_beh >= 1:
            severity = "HIGH"
            rationale.append(
                f"behavioural_gaps_HIGH={n_high_beh}>=1")
        elif n_total_beh >= self.HIGH_SEVERITY_BEHAVIOURAL_COUNT:
            severity = "HIGH"
            rationale.append(
                f"behavioural_gaps_count={n_total_beh}>="
                f"{self.HIGH_SEVERITY_BEHAVIOURAL_COUNT}_threshold")
        elif n_total_beh >= 1 and severity == "NONE":
            severity = "MEDIUM"
            rationale.append(
                f"behavioural_gaps_count={n_total_beh}_partial")

        if not rationale:
            rationale.append(
                "no_gaps_detected_against_segment_expectations")

        clv = intel.get("clv_estimate")
        clv_dec: Optional[Decimal] = None
        if clv is not None:
            try:
                clv_dec = Decimal(str(clv))
            except Exception:
                clv_dec = None

        return CustomerGap(
            customer_id=customer_id, segment=segment,
            products_held=products_held, expected_products=expected,
            portfolio_gap_count=portfolio_gap,
            propensity_gaps=propensities,
            behavioural_gaps=tuple(behavioural_gaps),
            overall_severity=severity,
            severity_rationale=tuple(rationale),
            clv_estimate_kes=clv_dec, found=True)

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def get_segment_gap_summary(self, segment: str) -> Dict[str, Any]:
        intel = self._load_intel()
        in_segment = [(cid, c) for cid, c in intel.items()
                      if c.get("segment") == segment]
        if not in_segment:
            return {"segment": segment, "ok": False,
                    "fallback_reason": "no_customers_in_segment",
                    "n_customers": 0}

        gaps = [self.analyze_customer_gap(cid) for cid, _ in in_segment]
        n_high = sum(1 for g in gaps if g.overall_severity == "HIGH")
        n_med = sum(1 for g in gaps if g.overall_severity == "MEDIUM")
        n_low = sum(1 for g in gaps if g.overall_severity == "NONE")

        # Top behavioural-need frequencies
        beh_freq: Dict[str, int] = {}
        for g in gaps:
            for b in g.behavioural_gaps:
                nid = b.get("need_id", "UNKNOWN")
                beh_freq[nid] = beh_freq.get(nid, 0) + 1

        avg_portfolio_gap = (
            sum(g.portfolio_gap_count for g in gaps) / len(gaps)
            if gaps else 0.0)

        # CLV at risk = HIGH severity customers' CLV total
        clv_at_risk = Decimal("0")
        for g in gaps:
            if g.overall_severity == "HIGH" and g.clv_estimate_kes:
                clv_at_risk += g.clv_estimate_kes

        return {
            "segment": segment,
            "ok": True,
            "n_customers": len(gaps),
            "n_high_severity": n_high,
            "n_medium_severity": n_med,
            "n_no_gaps": n_low,
            "avg_portfolio_gap": round(avg_portfolio_gap, 2),
            "top_behavioural_gaps": dict(
                sorted(beh_freq.items(), key=lambda x: -x[1])[:5]),
            "clv_at_risk_kes": str(clv_at_risk),
        }

    def get_top_unmet_needs(self, top_n: int = 10) -> List[Dict[str, Any]]:
        intel = self._load_intel()
        propensity_freq: Dict[str, int] = {}
        propensity_clv: Dict[str, Decimal] = {}
        for cid, c in intel.items():
            clv = c.get("clv_estimate") or 0
            try:
                clv_dec = Decimal(str(clv))
            except Exception:
                clv_dec = Decimal("0")
            for prop in c.get("propensity_scores", []):
                propensity_freq[prop] = propensity_freq.get(prop, 0) + 1
                propensity_clv[prop] = (propensity_clv.get(
                    prop, Decimal("0")) + clv_dec)

        # Composite score: frequency × clv_total (per propensity)
        ranked = sorted(propensity_freq.items(),
                         key=lambda x: -(x[1] * float(
                             propensity_clv.get(x[0], 0))))
        out: List[Dict[str, Any]] = []
        for prop, freq in ranked[:top_n]:
            out.append({
                "propensity": prop,
                "n_customers_with_propensity": freq,
                "total_clv_kes": str(propensity_clv.get(prop, Decimal("0"))),
            })
        return out

    def get_high_priority_gaps(
        self, min_clv: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        intel = self._load_intel()
        out: List[Dict[str, Any]] = []
        threshold = Decimal(str(min_clv)) if min_clv is not None else None
        for cid in intel.keys():
            g = self.analyze_customer_gap(cid)
            if g.overall_severity != "HIGH":
                continue
            if threshold is not None:
                if (g.clv_estimate_kes is None
                        or g.clv_estimate_kes < threshold):
                    continue
            out.append(g.as_dict())
        # Rank by CLV descending
        out.sort(
            key=lambda x: float(x.get("clv_estimate_kes") or 0),
            reverse=True)
        return out

    def bank_wide_gap_summary(self) -> Dict[str, Any]:
        intel = self._load_intel()
        if not intel:
            return {"ok": False,
                    "fallback_reason": "no_customer_intelligence_data",
                    "n_customers": 0}

        segments = sorted({c.get("segment") for c in intel.values()
                            if c.get("segment")})
        per_segment = {seg: self.get_segment_gap_summary(seg)
                        for seg in segments}

        total_n = len(intel)
        total_high = sum(s.get("n_high_severity", 0)
                          for s in per_segment.values()
                          if s.get("ok"))
        total_med = sum(s.get("n_medium_severity", 0)
                         for s in per_segment.values()
                         if s.get("ok"))
        total_low = total_n - total_high - total_med

        return {
            "ok": True,
            "n_customers_evaluated": total_n,
            "n_high_severity": total_high,
            "n_medium_severity": total_med,
            "n_no_gaps": total_low,
            "high_severity_rate_pct": round(
                100.0 * total_high / total_n, 2) if total_n else 0.0,
            "by_segment": per_segment,
        }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    eng = CustomerNeedsAnalyzer()
    intel = eng._load_intel()
    sample_id = next(iter(intel.keys()))
    print(f"Sample customer: {sample_id}")

    # Customer needs
    nr = eng.get_customer_needs(sample_id)
    print(f"  segment={nr.get('segment')} n_needs={nr.get('n_needs')}")
    for need in (nr.get("needs") or [])[:5]:
        print(f"    {need['priority']:>6}: {need['need_id']}")
    print()

    # Single-customer gap
    g = eng.analyze_customer_gap(sample_id)
    print(f"Gap analysis ({sample_id}):")
    print(f"  segment={g.segment} held={g.products_held}/{g.expected_products}")
    print(f"  portfolio_gap={g.portfolio_gap_count} severity={g.overall_severity}")
    print(f"  behavioural_gaps: {len(g.behavioural_gaps)}")
    print(f"  rationale: {g.severity_rationale}")
    print()

    # Bank-wide
    bw = eng.bank_wide_gap_summary()
    print(f"Bank-wide: n={bw['n_customers_evaluated']} "
          f"HIGH={bw['n_high_severity']} ({bw['high_severity_rate_pct']}%) "
          f"MED={bw['n_medium_severity']} NONE={bw['n_no_gaps']}")
    for seg, summary in bw.get("by_segment", {}).items():
        if summary.get("ok"):
            print(f"  {seg}: n={summary['n_customers']} "
                  f"HIGH={summary['n_high_severity']} "
                  f"avg_gap={summary['avg_portfolio_gap']}")
    print()

    # Top unmet needs
    top = eng.get_top_unmet_needs(top_n=5)
    print("Top unmet propensities:")
    for t in top:
        print(f"  {t['propensity']}: n={t['n_customers_with_propensity']} "
              f"clv_total={t['total_clv_kes']}")
    print()

    # High-priority gaps
    hp = eng.get_high_priority_gaps(min_clv=500000)
    print(f"High-priority gaps (CLV >= 500K): {len(hp)} customers")


if __name__ == "__main__":
    _self_test()
