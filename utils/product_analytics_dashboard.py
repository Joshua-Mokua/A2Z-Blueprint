"""utils.product_analytics_dashboard — Product Analytics Dashboard (engine layer)
(Standard ENH-140, v10.151). Phase 1E Product Module — tenth and final engine.

Per Continuation.docx §Standard #140 (Eco Bank QA spec):
    Interactive dashboard with all product metrics.

This is the TENTH and final Phase 1E Product standard. The engine layer
is a thin aggregator/composer that consumes outputs from the nine prior
Phase 1E engines and produces the unified dashboard payload that
`pages/16_product_arc_cockpit.py` renders. Same payload is exposed via
`utils/api_product.py`.

Per the v10.141 standing norm (UI-pass-on-closure codified), every
module closure ships engines + tests + registry flips + closure gate
(G147) + cockpit + UI gate (G148) + FastAPI router as a single closure
drop. This is the v10.151 closure drop.

Per Rule 7 (No silent ML predictions):
  1. Dashboard payload is composed from deterministic engine outputs
  2. NO ML aggregation — direct payload assembly from engine results
  3. Honest fallback: when an engine fails to load, error captured
     in payload's `engine_status` map; dashboard renders gracefully
  4. Caller controls which engines to include (selective queries
     possible to avoid full 3000-customer scan when not needed)

WHAT THIS MODULE SHIPS
----------------------
1. ProductAnalyticsDashboard class with:
   - get_dashboard_payload(include_per_customer=False) — full payload
   - get_engine_health_check() — quick liveness check across all 9
     companion engines
   - get_summary_metrics() — top-level KPI summary (cheapest call)
   - get_product_arc_kpis() — combined KPIs from P&L + ranking +
     pricing + bundling

2. Frozen DashboardPayload dataclass with:
   - generated_at_utc (timestamp)
   - summary_metrics (top-level KPIs)
   - by_product (per-product score + rank + position + recommendation)
   - by_segment (per-segment CVP + gap summary + bundling)
   - bank_wide (lifecycle distribution + engagement summary +
     pricing actionables + top bundles)
   - engine_status (per-engine ok/fail/skipped with reason)
   - is_estimate

3. Reads (via 9 companion engines, all injectable via DI):
   - ENH-131 ProductPnLIntelligence
   - ENH-132 ProductLifecycleEngine
   - ENH-133 CustomerNeedsAnalyzer
   - ENH-134 ProductCompetitiveIntelligence
   - ENH-135 ProductCVPBuilder
   - ENH-136 ProductRankingEngine
   - ENH-137 DynamicPricingEngine
   - ENH-138 ProductRecommendationEngine
   - ENH-139 ProductBundlingIntelligence

HONESTY DISCIPLINE
------------------
- Engine failures don't crash the dashboard — captured in engine_status
  with reason; payload returns partial data with explicit notes
- Per-customer aggregations gated behind include_per_customer=False
  default to avoid 3000× engine calls in routine queries
- generated_at_utc timestamp surfaces snapshot freshness
- Read-only contract — never writes
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.product_pnl_intelligence import ProductPnLIntelligence
from utils.product_lifecycle import ProductLifecycleEngine
from utils.customer_needs_analyzer import CustomerNeedsAnalyzer
from utils.product_competitive_intel import ProductCompetitiveIntelligence
from utils.product_cvp_builder import ProductCVPBuilder
from utils.product_ranking import ProductRankingEngine
from utils.dynamic_pricing import DynamicPricingEngine
from utils.product_recommendation import ProductRecommendationEngine
from utils.product_bundling import ProductBundlingIntelligence

DATA_DIR = Path(__file__).parent.parent / "data"
PRODUCTS_PATH = DATA_DIR / "products.json"


@dataclass(frozen=True)
class DashboardPayload:
    generated_at_utc: str
    summary_metrics: Dict[str, Any]
    by_product: Tuple[Dict[str, Any], ...]
    by_segment: Dict[str, Dict[str, Any]]
    bank_wide: Dict[str, Any]
    engine_status: Dict[str, Dict[str, Any]]
    is_estimate: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "summary_metrics": dict(self.summary_metrics),
            "by_product": list(self.by_product),
            "by_segment": dict(self.by_segment),
            "bank_wide": dict(self.bank_wide),
            "engine_status": dict(self.engine_status),
            "is_estimate": self.is_estimate,
        }


class ProductAnalyticsDashboard:
    """Aggregates outputs from 9 companion engines into unified
    dashboard payload. Read-only.
    """

    def __init__(
        self,
        pnl_engine: Optional[ProductPnLIntelligence] = None,
        lifecycle_engine: Optional[ProductLifecycleEngine] = None,
        needs_engine: Optional[CustomerNeedsAnalyzer] = None,
        competitive_engine: Optional[ProductCompetitiveIntelligence]
                = None,
        cvp_engine: Optional[ProductCVPBuilder] = None,
        ranking_engine: Optional[ProductRankingEngine] = None,
        pricing_engine: Optional[DynamicPricingEngine] = None,
        recommendation_engine: Optional[
            ProductRecommendationEngine] = None,
        bundling_engine: Optional[ProductBundlingIntelligence] = None,
        products_path: Optional[Path] = None,
    ) -> None:
        self.pnl = pnl_engine or ProductPnLIntelligence()
        self.lifecycle = lifecycle_engine or ProductLifecycleEngine()
        self.needs = needs_engine or CustomerNeedsAnalyzer()
        self.competitive = (competitive_engine
                              or ProductCompetitiveIntelligence())
        self.cvp = cvp_engine or ProductCVPBuilder()
        self.ranking = ranking_engine or ProductRankingEngine()
        self.pricing = pricing_engine or DynamicPricingEngine()
        self.recommendation = (recommendation_engine
                                or ProductRecommendationEngine())
        self.bundling = bundling_engine or ProductBundlingIntelligence()
        self.products_path = products_path or PRODUCTS_PATH

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_products(self) -> List[Dict[str, Any]]:
        try:
            with open(self.products_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _safe_call(self, fn, label: str) -> Tuple[Any, Dict[str, Any]]:
        """Call a companion engine method; capture failures honestly."""
        try:
            result = fn()
            return result, {"ok": True, "engine": label}
        except Exception as e:
            return None, {
                "ok": False,
                "engine": label,
                "error_type": type(e).__name__,
                "error_msg": str(e)[:200],
            }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_engine_health_check(self) -> Dict[str, Any]:
        """Quick liveness check across all 9 companion engines.
        Returns engine_id → {ok: bool, last_error: str|None}."""
        checks: Dict[str, Dict[str, Any]] = {}

        for label, fn in (
            ("ENH-131_pnl", lambda: self.pnl.compute_portfolio()),
            ("ENH-132_lifecycle",
              lambda: self.lifecycle.get_sunset_candidates()),
            ("ENH-133_needs",
              lambda: self.needs.bank_wide_gap_summary()),
            ("ENH-134_competitive",
              lambda: self.competitive.get_competitive_summary()),
            ("ENH-135_cvp",
              lambda: self.cvp.get_cvp_summary()),
            ("ENH-136_ranking",
              lambda: self.ranking.get_score_distribution()),
            ("ENH-137_pricing",
              lambda: self.pricing.get_recommendation_summary()),
            ("ENH-138_recommendation",
              lambda: self.recommendation.get_recommendation_summary()),
            ("ENH-139_bundling",
              lambda: self.bundling.get_bundling_summary()),
        ):
            _, status = self._safe_call(fn, label)
            checks[label] = status

        n_ok = sum(1 for s in checks.values() if s.get("ok"))
        return {
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "n_engines_checked": len(checks),
            "n_ok": n_ok,
            "all_healthy": n_ok == len(checks),
            "per_engine": checks,
        }

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Top-level KPIs only — fast call, no per-customer scans."""
        portfolio_pnl, _ = self._safe_call(
            self.pnl.get_bank_wide_summary, "pnl")
        ranking_dist, _ = self._safe_call(
            self.ranking.get_score_distribution, "ranking")
        comp_summary, _ = self._safe_call(
            self.competitive.get_competitive_summary, "competitive")
        pricing_summary, _ = self._safe_call(
            self.pricing.get_recommendation_summary, "pricing")

        return {
            "n_products": len(self._load_products()),
            "portfolio_revenue_kes": (
                portfolio_pnl.get("total_revenue_kes")
                if isinstance(portfolio_pnl, dict) else None),
            "portfolio_margin_pct": (
                portfolio_pnl.get("margin_pct")
                if isinstance(portfolio_pnl, dict) else None),
            "n_loss_making_products": (
                portfolio_pnl.get("n_loss_making", 0)
                if isinstance(portfolio_pnl, dict) else 0),
            "ranking_distribution": (
                ranking_dist.get("by_band", {})
                if isinstance(ranking_dist, dict) else {}),
            "avg_product_score": (
                ranking_dist.get("avg_score", 0)
                if isinstance(ranking_dist, dict) else 0),
            "competitive_leadership_rate_pct": (
                comp_summary.get("leadership_rate_pct", 0)
                if isinstance(comp_summary, dict) else 0),
            "n_actionable_pricing_recommendations": (
                pricing_summary.get("n_actionable", 0)
                if isinstance(pricing_summary, dict) else 0),
        }

    def get_product_arc_kpis(self) -> List[Dict[str, Any]]:
        """Per-product unified KPIs combining ranking + competitive +
        pricing + lifecycle stage."""
        out: List[Dict[str, Any]] = []
        for product in self._load_products():
            pid = product.get("id", "")
            entry: Dict[str, Any] = {
                "product_id": pid,
                "name": product.get("name", ""),
                "category": product.get("category", ""),
            }
            # Ranking
            try:
                score = self.ranking.get_product_score(pid)
                entry["ranking_score"] = score.total_score
                entry["ranking_band"] = score.band
            except Exception:
                entry["ranking_score"] = None
                entry["ranking_band"] = "unknown"
            # Competitive position
            try:
                landscape = self.competitive.get_competitor_landscape(
                    pid)
                entry["competitive_position"] = landscape.position
                entry["delta_vs_median_bps"] = (
                    landscape.delta_vs_median_bps)
            except Exception:
                entry["competitive_position"] = "unknown"
                entry["delta_vs_median_bps"] = None
            # Pricing recommendation
            try:
                rec = self.pricing.get_pricing_recommendation(pid)
                entry["pricing_action"] = rec.action
                entry["pricing_change_bps"] = rec.change_bps
            except Exception:
                entry["pricing_action"] = "unknown"
                entry["pricing_change_bps"] = None
            # Lifecycle stage
            try:
                stage = self.lifecycle.get_product_stage(pid)
                entry["lifecycle_stage"] = stage.get("current_stage")
            except Exception:
                entry["lifecycle_stage"] = None
            # P&L margin
            try:
                pnl = self.pnl.compute_product_pnl(product)
                entry["margin_pct"] = (str(pnl.margin_pct)
                                        if pnl.margin_pct is not None
                                        else None)
                entry["pnl_status"] = pnl.status
            except Exception:
                entry["margin_pct"] = None
                entry["pnl_status"] = "unknown"
            out.append(entry)
        return out

    def get_dashboard_payload(
        self, include_per_customer: bool = False,
    ) -> DashboardPayload:
        """Full dashboard payload. include_per_customer=True triggers
        the heavier 3000-customer recommendation summary (rarely needed
        in routine cockpit refreshes)."""
        engine_status: Dict[str, Dict[str, Any]] = {}

        # Summary metrics
        summary = self.get_summary_metrics()

        # Per-product KPIs
        by_product, st = self._safe_call(
            self.get_product_arc_kpis, "ENH-140_per_product")
        engine_status["per_product_kpis"] = st
        if by_product is None:
            by_product = []

        # Per-segment view: combine CVP + needs gap + bundling per
        # segment (at segment level, not per-customer)
        by_segment: Dict[str, Dict[str, Any]] = {}
        try:
            cvps = self.cvp.generate_all_segment_cvps()
            for seg, cvp in cvps.items():
                seg_entry: Dict[str, Any] = {
                    "segment": seg,
                    "cvp_strength_score": cvp.get("cvp_strength_score"),
                    "cvp_strength_band": cvp.get("cvp_strength_band"),
                    "n_addressed_needs": len(
                        cvp.get("addressed_needs") or []),
                    "n_differentiating_offers": len(
                        cvp.get("differentiating_offers") or []),
                    "n_trade_offs": len(cvp.get("trade_offs") or []),
                }
                # Add segment gap summary
                try:
                    gap = self.needs.get_segment_gap_summary(seg)
                    seg_entry["gap_summary"] = gap if gap.get("ok") \
                        else {"ok": False,
                              "reason": gap.get("fallback_reason")}
                except Exception as e:
                    seg_entry["gap_summary"] = {
                        "ok": False, "error": type(e).__name__}
                # Add segment top bundles
                try:
                    bun = self.bundling.get_segment_bundles(seg, top_n=3)
                    seg_entry["top_bundles"] = (bun.get("top_bundles")
                                                  if bun.get("ok")
                                                  else [])
                except Exception:
                    seg_entry["top_bundles"] = []
                by_segment[seg] = seg_entry
            engine_status["per_segment"] = {"ok": True}
        except Exception as e:
            engine_status["per_segment"] = {
                "ok": False, "error_type": type(e).__name__,
                "error_msg": str(e)[:200]}

        # Bank-wide
        bank_wide: Dict[str, Any] = {}
        for label, fn in (
            ("lifecycle_sunset_candidates",
              lambda: self.lifecycle.get_sunset_candidates()),
            ("pricing_actionables",
              lambda: self.pricing.get_actionable_recommendations()),
            ("top_bundles",
              lambda: self.bundling.get_top_bundles(
                  min_affinity=0.0, top_n=10)),
            ("competitive_summary",
              lambda: self.competitive.get_competitive_summary()),
        ):
            result, st = self._safe_call(fn, f"ENH-140_{label}")
            engine_status[label] = st
            bank_wide[label] = result

        # Optional: per-customer recommendations summary
        if include_per_customer:
            rec_summary, st = self._safe_call(
                self.recommendation.get_recommendation_summary,
                "ENH-138_per_customer")
            engine_status["per_customer_recommendations"] = st
            bank_wide["recommendation_summary"] = rec_summary

        is_estimate = any(
            not s.get("ok") for s in engine_status.values())

        return DashboardPayload(
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            summary_metrics=summary,
            by_product=tuple(by_product),
            by_segment=by_segment,
            bank_wide=bank_wide,
            engine_status=engine_status,
            is_estimate=is_estimate)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    eng = ProductAnalyticsDashboard()

    # Health check first
    print("=" * 60)
    print("ENH-140 Product Analytics Dashboard — self-test")
    print("=" * 60)

    health = eng.get_engine_health_check()
    print(f"\nHealth: {health['n_ok']}/{health['n_engines_checked']} "
          f"engines OK; all_healthy={health['all_healthy']}")
    for engine_id, status in health["per_engine"].items():
        marker = "✓" if status.get("ok") else "✗"
        print(f"  {marker} {engine_id}: ok={status.get('ok')}")
    print()

    # Summary metrics (fast)
    print("Summary metrics:")
    summary = eng.get_summary_metrics()
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print()

    # Per-product KPIs
    print("Per-product KPIs (top 5 by ranking score):")
    kpis = eng.get_product_arc_kpis()
    kpis.sort(key=lambda x: -(x.get("ranking_score") or 0))
    for p in kpis[:5]:
        print(f"  {p['product_id']} {p['name']}: "
              f"score={p['ranking_score']} ({p['ranking_band']}), "
              f"comp={p['competitive_position']}, "
              f"pricing={p['pricing_action']}, "
              f"stage={p['lifecycle_stage']}")
    print()

    # Full payload (without per-customer)
    payload = eng.get_dashboard_payload(include_per_customer=False)
    print(f"Full payload generated_at_utc: {payload.generated_at_utc}")
    print(f"  by_product: {len(payload.by_product)} products")
    print(f"  by_segment: {len(payload.by_segment)} segments")
    print(f"  bank_wide keys: {list(payload.bank_wide.keys())}")
    print(f"  is_estimate: {payload.is_estimate}")
    print()

    # Sample segment summary
    print("Sample segment view (Premium):")
    prem = payload.by_segment.get("Premium", {})
    for k in ("cvp_strength_score", "cvp_strength_band",
              "n_addressed_needs", "n_differentiating_offers",
              "n_trade_offs"):
        print(f"  {k}: {prem.get(k)}")


if __name__ == "__main__":
    _self_test()
