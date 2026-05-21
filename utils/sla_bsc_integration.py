"""
================================================================================
A2Z MIS 360 — Standard #386: SLA Integration with BSC
================================================================================

Risk classification: Cat B (deterministic BSC scoring adapter)

SLA compliance feeds Operations & Compliance pillar of BSC.
Auto-scoring per role + branch + cluster.

Public API:
    sla_to_bsc_score(compliance_pct)             -- 1–5 BSC scale
    submit_sla_actuals(period, mode)             -- pushes to BSC
    bsc_pillar_summary(period)                   -- per-pillar SLA roll-up

BSC scoring scale byte-for-byte (consistent with utils/bsc_engine.py):
    5 -- 100%+ achievement (≥98% compliance)
    4 -- ≥95% compliance
    3 -- ≥90% compliance
    2 -- ≥85% compliance
    1 -- <85% compliance

Submission modes byte-for-byte (consistent with v5.49 #29 pattern):
    strict -- DEFAULT — provisional/no-data SLAs SKIPPED
    warn   -- submitted with is_provisional=True flag
    all    -- forced (data-quality remediation only)

Honesty rules:
    Rule 1: bsc_score = None when compliance_pct is None
    Rule 4 default-strict: SLAs without observations SKIPPED in strict mode

================================================================================
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.sla_registry import SlaRegistryEngine
from utils.sla_monitoring import SlaMonitoringEngine

getcontext().prec = 28

# BSC pillar mapping for SLAs — per Continuation.docx
SLA_BSC_PILLAR_MAP: Dict[str, str] = {
    "CUSTOMER":   "Customer",
    "INTERNAL":   "Internal Process",
    "VENDOR":     "Internal Process",
    "REGULATORY": "Operations & Compliance",
}

# BSC score thresholds (compliance % → 1-5 scale)
BSC_SCORE_5_THRESHOLD: Decimal = Decimal("98")
BSC_SCORE_4_THRESHOLD: Decimal = Decimal("95")
BSC_SCORE_3_THRESHOLD: Decimal = Decimal("90")
BSC_SCORE_2_THRESHOLD: Decimal = Decimal("85")

SUBMISSION_MODES: Tuple[str, ...] = ("strict", "warn", "all")


def sla_to_bsc_score(compliance_pct: Optional[Decimal]) -> Optional[int]:
    """
    Convert compliance % to 1-5 BSC score.

    Rule 1: returns None if compliance_pct is None.
    """
    if compliance_pct is None:
        return None
    cp = Decimal(str(compliance_pct))
    if cp >= BSC_SCORE_5_THRESHOLD:
        return 5
    elif cp >= BSC_SCORE_4_THRESHOLD:
        return 4
    elif cp >= BSC_SCORE_3_THRESHOLD:
        return 3
    elif cp >= BSC_SCORE_2_THRESHOLD:
        return 2
    return 1


class SlaBscIntegrationEngine:
    """
    SLA → BSC adapter. Composes registry + monitoring engines into
    BSC submission payload.
    """

    def __init__(
        self,
        registry: Optional[SlaRegistryEngine] = None,
        monitoring: Optional[SlaMonitoringEngine] = None,
        bsc_submit_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ):
        self.registry = registry or SlaRegistryEngine()
        self.monitoring = monitoring or SlaMonitoringEngine()
        self.bsc_submit_fn = bsc_submit_fn or self._default_bsc_submit
        # In-memory log of submissions for testability
        self._submission_log: List[Dict[str, Any]] = []

    def _default_bsc_submit(self, payload: Dict[str, Any]) -> bool:
        """No-op default; logs to in-memory list (testable)."""
        self._submission_log.append(payload)
        return True

    def submit_sla_actuals(
        self,
        period_start: str,
        period_end: str,
        mode: str = "strict",
    ) -> Dict[str, Any]:
        """
        Submit SLA compliance to BSC.

        Mode behavior (Rule 4 default-strict):
            strict -- skip SLAs without observations
            warn   -- submit with is_provisional flag
            all    -- submit everything

        Returns: {submitted, skipped, by_pillar, errors}
        """
        if mode not in SUBMISSION_MODES:
            return {
                "submitted": [],
                "skipped": [],
                "errors": [f"invalid_mode:{mode}"],
            }

        active_slas = self.registry.list_slas(status="ACTIVE")

        submitted = []
        skipped = []
        by_pillar: Dict[str, List[Dict[str, Any]]] = {}

        for sla in active_slas:
            sid = sla.get("sla_id")
            comp = self.monitoring.compute_compliance(sid, period_start, period_end)

            # Rule 1 + 4 default-strict: skip if no observations
            if comp["compliance_pct"] is None:
                if mode == "strict":
                    skipped.append({
                        "sla_id": sid,
                        "reason": "no_observations_strict_mode",
                    })
                    continue
                elif mode == "warn":
                    payload = self._build_payload(
                        sla, comp, period_start, period_end,
                        is_provisional=True,
                    )
                    self.bsc_submit_fn(payload)
                    submitted.append(payload)
                    pillar = payload["bsc_pillar"]
                    by_pillar.setdefault(pillar, []).append(payload)
                    continue
                # mode == "all" → fall through

            payload = self._build_payload(
                sla, comp, period_start, period_end, is_provisional=False
            )
            self.bsc_submit_fn(payload)
            submitted.append(payload)
            pillar = payload["bsc_pillar"]
            by_pillar.setdefault(pillar, []).append(payload)

        return {
            "submitted": submitted,
            "skipped": skipped,
            "by_pillar": {k: len(v) for k, v in by_pillar.items()},
            "mode": mode,
            "period": f"{period_start} to {period_end}",
            "total_submitted": len(submitted),
            "total_skipped": len(skipped),
            "errors": [],
        }

    def _build_payload(
        self,
        sla: Dict[str, Any],
        comp: Dict[str, Any],
        period_start: str,
        period_end: str,
        is_provisional: bool,
    ) -> Dict[str, Any]:
        compliance_pct = comp.get("compliance_pct")
        if compliance_pct is not None:
            compliance_pct = Decimal(str(compliance_pct))
        bsc_score = sla_to_bsc_score(compliance_pct)

        sla_type = sla.get("sla_type", "INTERNAL")
        pillar = SLA_BSC_PILLAR_MAP.get(sla_type, "Internal Process")

        return {
            "sla_id": sla.get("sla_id"),
            "kpi_id": f"SLA_{sla.get('sla_id')}",
            "sla_name": sla.get("name"),
            "bsc_pillar": pillar,
            "bsc_score": bsc_score,
            "compliance_pct": (
                str(compliance_pct) if compliance_pct is not None else None
            ),
            "period_start": period_start,
            "period_end": period_end,
            "owner_department": sla.get("owner_department"),
            "priority": sla.get("priority"),
            "is_provisional": is_provisional,
            "source_module": "sla_bsc_integration.v10.271",
        }

    def bsc_pillar_summary(
        self,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """Per-pillar SLA roll-up."""
        result = self.submit_sla_actuals(period_start, period_end, mode="strict")

        # Group submitted SLAs by pillar
        pillar_data: Dict[str, List[int]] = {}
        for s in result["submitted"]:
            pillar = s["bsc_pillar"]
            score = s["bsc_score"]
            if score is not None:
                pillar_data.setdefault(pillar, []).append(score)

        summary = {}
        for pillar, scores in pillar_data.items():
            avg_score = sum(scores) / len(scores) if scores else None
            summary[pillar] = {
                "sla_count": len(scores),
                "avg_bsc_score": (
                    round(avg_score, 2) if avg_score is not None else None
                ),
                "min_bsc_score": min(scores) if scores else None,
                "max_bsc_score": max(scores) if scores else None,
            }

        return {
            "period": f"{period_start} to {period_end}",
            "by_pillar": summary,
            "total_slas_in_bsc": result["total_submitted"],
            "skipped_count": result["total_skipped"],
        }


def _self_test() -> None:
    import tempfile
    from pathlib import Path

    # Test sla_to_bsc_score
    assert sla_to_bsc_score(Decimal("99")) == 5
    assert sla_to_bsc_score(Decimal("96")) == 4
    assert sla_to_bsc_score(Decimal("92")) == 3
    assert sla_to_bsc_score(Decimal("87")) == 2
    assert sla_to_bsc_score(Decimal("70")) == 1
    assert sla_to_bsc_score(None) is None  # Rule 1

    with tempfile.TemporaryDirectory() as tmpdir:
        registry = SlaRegistryEngine(
            registry_path=Path(tmpdir) / "sla_registry.json"
        )
        monitoring = SlaMonitoringEngine(
            observations_path=Path(tmpdir) / "sla_observations.json"
        )

        # Register SLAs across pillars
        registry.register_sla({
            "sla_id": "SLA-CUST-A",
            "name": "Customer Inquiry Response",
            "sla_type": "CUSTOMER",
            "priority": "P2_HIGH",
            "metric_type": "RESPONSE_TIME",
            "target_value": Decimal("2"), "target_unit": "hours",
            "direction": "max",
            "owner_department": "Retail",
        })
        registry.register_sla({
            "sla_id": "SLA-REG-A",
            "name": "CBK 30-day Resolution",
            "sla_type": "REGULATORY",
            "priority": "P1_CRITICAL",
            "metric_type": "RESPONSE_TIME",
            "target_value": Decimal("30"), "target_unit": "days",
            "direction": "max",
            "owner_department": "Compliance",
            "regulatory_ref": "CBK PG/09",
        })

        # Add observations to one SLA only
        for i in range(10):
            monitoring.record_event(
                "SLA-CUST-A", f"E-{i}",
                "2026-04-01T10:00:00", "2026-04-01T11:30:00",
                Decimal("1.5"), Decimal("2"), "max",
            )

        engine = SlaBscIntegrationEngine(
            registry=registry, monitoring=monitoring
        )

        # Test 1: strict mode skips SLA-REG-A (no observations)
        result = engine.submit_sla_actuals(
            "2026-04-01", "2026-04-30", mode="strict"
        )
        assert result["total_submitted"] == 1
        assert result["total_skipped"] == 1
        assert result["skipped"][0]["sla_id"] == "SLA-REG-A"

        # Test 2: warn mode submits both with provisional flag
        engine2 = SlaBscIntegrationEngine(
            registry=registry, monitoring=monitoring
        )
        result2 = engine2.submit_sla_actuals(
            "2026-04-01", "2026-04-30", mode="warn"
        )
        assert result2["total_submitted"] == 2
        # SLA-REG-A should be marked provisional
        provisional = [s for s in result2["submitted"] if s["is_provisional"]]
        assert len(provisional) == 1
        assert provisional[0]["sla_id"] == "SLA-REG-A"

        # Test 3: invalid mode rejected
        result3 = engine.submit_sla_actuals(
            "2026-04-01", "2026-04-30", mode="bogus"
        )
        assert "invalid_mode:bogus" in result3["errors"]

        # Test 4: pillar mapping
        cust_payload = next(
            s for s in result["submitted"] if s["sla_id"] == "SLA-CUST-A"
        )
        assert cust_payload["bsc_pillar"] == "Customer"

        # Test 5: pillar summary
        summary = engine.bsc_pillar_summary("2026-04-01", "2026-04-30")
        assert "Customer" in summary["by_pillar"]
        assert summary["by_pillar"]["Customer"]["sla_count"] == 1

    print("  ✅ sla_bsc_integration self-test PASS")


if __name__ == "__main__":
    _self_test()
