"""tests/test_performance_insights.py — Standard #20 tests.

Includes synthetic latency harness (G31 artifact).
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
LATENCY_RESULTS = ROOT / "api_v2_latency_results.json"


class TestStandard20Files:
    def test_service_module_exists(self):
        assert (ROOT / "utils" / "performance_insights.py").exists()


@pytest.fixture
def patched_lookup(monkeypatch):
    """Patch _staff_lookup so unknown-staff path returns None."""
    from utils import performance_insights as pi
    monkeypatch.setattr(
        pi, "_staff_lookup",
        lambda sc: {"full_name": "Test", "role": "X"} if sc.startswith("S") else None,
    )


class TestSpecContract:
    def test_returns_required_keys(self, patched_lookup):
        from utils.performance_insights import get_performance_insights
        r = get_performance_insights(
            "S001",
            kpi_status_fn=lambda sc: [
                {"kpi_id": "DEP_GROWTH", "achievement_pct": 130}
            ],
            growth_plan_fn=lambda sc: {"promotion_readiness": 0.75},
            overall_score_fn=lambda sc, p: 3.8,
        )
        assert "overall_score" in r
        assert "strengths" in r
        assert "promotion_readiness" in r

    def test_strengths_threshold(self, patched_lookup):
        from utils.performance_insights import get_performance_insights
        r = get_performance_insights(
            "S001",
            kpi_status_fn=lambda sc: [
                {"kpi_id": "ABOVE", "achievement_pct": 130},   # qualifies
                {"kpi_id": "AT_THRESHOLD", "achievement_pct": 110},  # qualifies
                {"kpi_id": "BELOW", "achievement_pct": 109},   # excluded
            ],
            growth_plan_fn=lambda sc: {},
            overall_score_fn=lambda sc, p: 3.5,
        )
        assert "ABOVE" in r["strengths"]
        assert "AT_THRESHOLD" in r["strengths"]
        assert "BELOW" not in r["strengths"]

    def test_strengths_sorted_desc(self, patched_lookup):
        from utils.performance_insights import get_performance_insights
        r = get_performance_insights(
            "S001",
            kpi_status_fn=lambda sc: [
                {"kpi_id": "K3", "achievement_pct": 115},
                {"kpi_id": "K1", "achievement_pct": 150},
                {"kpi_id": "K2", "achievement_pct": 130},
            ],
            growth_plan_fn=lambda sc: {},
            overall_score_fn=lambda sc, p: 4.0,
        )
        assert r["strengths"] == ["K1", "K2", "K3"]

    def test_strengths_capped_at_5(self, patched_lookup):
        from utils.performance_insights import get_performance_insights
        rows = [{"kpi_id": f"K{i}", "achievement_pct": 200 - i}
                for i in range(10)]
        r = get_performance_insights(
            "S001",
            kpi_status_fn=lambda sc: rows,
            growth_plan_fn=lambda sc: {},
            overall_score_fn=lambda sc, p: 4.0,
        )
        assert len(r["strengths"]) == 5

    def test_promotion_readiness_clamped(self, patched_lookup):
        from utils.performance_insights import get_performance_insights
        r = get_performance_insights(
            "S001",
            kpi_status_fn=lambda sc: [],
            growth_plan_fn=lambda sc: {"promotion_readiness": 1.5},
            overall_score_fn=lambda sc, p: None,
        )
        assert r["promotion_readiness"] == 1.0

        r = get_performance_insights(
            "S001",
            kpi_status_fn=lambda sc: [],
            growth_plan_fn=lambda sc: {"promotion_readiness": -0.5},
            overall_score_fn=lambda sc, p: None,
        )
        assert r["promotion_readiness"] == 0.0


class TestDefensiveContract:
    def test_unknown_staff_returns_empty(self, patched_lookup):
        from utils.performance_insights import get_performance_insights
        r = get_performance_insights(
            "UNKNOWN",
            kpi_status_fn=lambda sc: [],
            growth_plan_fn=lambda sc: {},
            overall_score_fn=lambda sc, p: None,
        )
        assert r == {}

    def test_empty_staff_code_returns_empty(self, patched_lookup):
        from utils.performance_insights import get_performance_insights
        assert get_performance_insights("") == {}

    def test_no_data_graceful_zeros(self, patched_lookup):
        from utils.performance_insights import get_performance_insights
        r = get_performance_insights(
            "S001",
            kpi_status_fn=lambda sc: [],
            growth_plan_fn=lambda sc: {},
            overall_score_fn=lambda sc, p: None,
        )
        # Staff exists, no signals → spec fields present with zeros
        assert r["overall_score"] == 0.0
        assert r["strengths"] == []
        assert r["promotion_readiness"] == 0.0


class TestPctToScore:
    def test_score_bands(self):
        from utils.performance_insights import _pct_to_score
        assert _pct_to_score(150) == 5.0
        assert _pct_to_score(120) == 4.5
        assert _pct_to_score(100) == 4.0
        assert _pct_to_score(90) == 3.5
        assert _pct_to_score(80) == 3.0
        assert _pct_to_score(0) == 1.0


class TestMetaBlock:
    def test_meta_traceability(self, patched_lookup):
        from utils.performance_insights import get_performance_insights
        r = get_performance_insights(
            "S001",
            kpi_status_fn=lambda sc: [{"kpi_id": "K1", "achievement_pct": 130}],
            growth_plan_fn=lambda sc: {"promotion_readiness": 0.75},
            overall_score_fn=lambda sc, p: 3.8,
        )
        assert "meta" in r
        assert r["meta"]["staff_code"] == "S001"
        assert "signals_present" in r["meta"]


class TestApiRouteWired:
    """Verify the route is in utils/api.py and declares auth."""

    def test_route_defined(self):
        api_src = (ROOT / "utils" / "api.py").read_text()
        assert "/api/v2/performance/insights/" in api_src

    def test_route_has_auth(self):
        api_src = (ROOT / "utils" / "api.py").read_text()
        # Find the route block and confirm auth dep is in the signature
        idx = api_src.find("/api/v2/performance/insights/")
        assert idx > 0
        # Look for Depends(get_current_user) within ~500 chars after route
        snippet = api_src[idx:idx + 1000]
        assert "Depends(get_current_user)" in snippet


# ═══════════════════════════════════════════════════════════════════════
# Synthetic latency harness — G31 artifact
# ═══════════════════════════════════════════════════════════════════════

def test_service_latency_under_500ms():
    """Run get_performance_insights repeatedly; measure synthetic latency.

    Spec target: <500ms (the spec says "webhooks <5s", we use a tighter
    bar for the synthetic call duration on a single request).
    """
    from utils.performance_insights import get_performance_insights
    import utils.performance_insights as pi

    # Patch staff lookup so the call returns non-empty
    original_lookup = pi._staff_lookup
    pi._staff_lookup = lambda sc: {"full_name": "T", "role": "X"} if sc.startswith("S") else None

    try:
        # Warm-up
        for _ in range(3):
            get_performance_insights(
                "S001",
                kpi_status_fn=lambda sc: [
                    {"kpi_id": f"K{i}", "achievement_pct": 100 + i} for i in range(20)
                ],
                growth_plan_fn=lambda sc: {"promotion_readiness": 0.7},
                overall_score_fn=lambda sc, p: 3.8,
            )

        N = 50
        durations_ms = []
        for _ in range(N):
            t0 = time.perf_counter()
            get_performance_insights(
                "S001",
                kpi_status_fn=lambda sc: [
                    {"kpi_id": f"K{i}", "achievement_pct": 100 + i} for i in range(20)
                ],
                growth_plan_fn=lambda sc: {"promotion_readiness": 0.7},
                overall_score_fn=lambda sc, p: 3.8,
            )
            durations_ms.append((time.perf_counter() - t0) * 1000)
    finally:
        pi._staff_lookup = original_lookup

    durations_ms.sort()
    p50 = durations_ms[len(durations_ms) // 2]
    p95 = durations_ms[int(len(durations_ms) * 0.95)]
    avg = sum(durations_ms) / len(durations_ms)
    max_ms = max(durations_ms)

    artifact = {
        "schema_version": 1,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "samples": N,
        "p50_ms": round(p50, 3),
        "p95_ms": round(p95, 3),
        "avg_ms": round(avg, 3),
        "max_ms": round(max_ms, 3),
        "spec_target_ms": 500.0,
        "all_passed": p95 < 500.0,
    }
    LATENCY_RESULTS.write_text(json.dumps(artifact, indent=2))

    assert p95 < 500.0, (
        f"p95 latency {p95:.1f}ms exceeds 500ms spec target"
    )
