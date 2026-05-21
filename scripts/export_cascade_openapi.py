"""scripts/export_cascade_openapi.py — Filter OpenAPI to cascade routes only.

Per v10.413 (E7): React team needs a focused OpenAPI spec covering just
the /api/v1/cascade/* surface for TypeScript client generation.

Companion to scripts/export_openapi.py which exports the FULL spec.
This script exports ONLY the cascade endpoints — useful for:
  - Generating a React/TypeScript client scoped to cascade work
  - Contract-testing the cascade router in isolation
  - Documenting the v10.413 API surface

Usage:
  python scripts/export_cascade_openapi.py
  # writes to docs/openapi_cascade_v10413.json

Shipped: v10.413.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


# Expected endpoints (used both for export validation and gate check)
EXPECTED_ENDPOINTS = [
    "/api/v1/cascade/health/summary",
    "/api/v1/cascade/health/pillars",
    "/api/v1/cascade/health/sbu",
    "/api/v1/cascade/health/kpis",
    "/api/v1/cascade/health/broken-chains",
    "/api/v1/cascade/health/stale-entries",
    "/api/v1/cascade/rollup/{manager_code}/{period}",
    "/api/v1/cascade/pillars/bank-weights",
    "/api/v1/cascade/pillars/staff/{staff_code}/{period}",
    "/api/v1/cascade/pairing/shared-kpis",
    "/api/v1/cascade/pairing/co-owners/{kpi}",
    "/api/v1/cascade/pairing/apply",
    "/api/v1/cascade/simulator/current/{manager_code}/{kpi}/{period}",
    "/api/v1/cascade/simulator/split",
    # Capacity feedback (older v10.412 stub, mounted v10.413)
    "/api/cascade/capacity-feedback",
    "/api/v1/cascade/structure/audit-summary",
]


def export(output: str = "docs/openapi_cascade_v10413.json") -> int:
    # Build a STANDALONE FastAPI app with both cascade routers.
    # This avoids any forward-ref issues in legacy api.py models.
    try:
        from fastapi import FastAPI
        from utils.api_cascade import router as cascade_router
    except ImportError as e:
        print(f"ERROR: cannot import cascade router: {e}", file=sys.stderr)
        return 1

    standalone = FastAPI(
        title="A2Z Blueprint Cascade API",
        version="10.413.0",
        description=(
            "FastAPI endpoints for the Target Cascade module. "
            "All endpoints require JWT bearer authentication. "
            "Built v10.413 (E7) per React front-end requirement. "
            "Wraps pure-compute engines: cascade_health_engine, "
            "manager_rollup, pillar_impact_engine, "
            "kpi_ownership_pairing, target_scenario_simulator, "
            "capacity_feedback_engine, cascade_structure_engine."
        ),
    )
    standalone.include_router(cascade_router)
    # Also include capacity router (v10.412 stub, now mounted v10.413)
    try:
        from utils.api_capacity_feedback import router as capacity_router
        standalone.include_router(capacity_router)
    except ImportError:
        pass

    full = standalone.openapi()

    cascade_paths = {
        p: methods for p, methods in full.get("paths", {}).items()
        if "/api/v1/cascade" in p or "/api/cascade" in p
    }

    cascade_schema = {
        "openapi": full.get("openapi", "3.0.0"),
        "info": full.get("info", {}),
        "servers": [{"url": "http://localhost:8502"}],
        "paths": cascade_paths,
        "components": full.get("components", {"schemas": {}}),
        "tags": [{"name": "cascade",
                  "description": "Target cascade module endpoints"}],
    }

    out_path = REPO / output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(cascade_schema, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"✓ Wrote cascade OpenAPI spec to {out_path}")
    print(f"  Endpoints exported: {len(cascade_paths)}")

    missing = [p for p in EXPECTED_ENDPOINTS if p not in cascade_paths]
    if missing:
        print(f"\n⚠️  Missing expected endpoints ({len(missing)}):")
        for p in missing:
            print(f"   {p}")
        return 2

    print(f"  All {len(EXPECTED_ENDPOINTS)} expected endpoints present ✓")
    return 0


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "docs/openapi_cascade_v10413.json"
    sys.exit(export(output))
