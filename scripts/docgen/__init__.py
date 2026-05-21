"""scripts/docgen — A2Z Living Documentation System (v8.12+).

Per `docs/A2Z_LIVING_DOCS_PLAN.md` (v8.11), this package renders sales-grade
collateral from the existing tier 1-5 registries (system_stocks, system_flows,
system_invariants, composite_scores, kpi_library, charter, retrospectives,
CHANGELOGs, audit.py).

v8.12 ships:
    - _registry_loader.py — assembles the unified content dict
    - _claim_validator.py — verifies claims trace to the registry
    - 6 sales-content JSON files in docs/sales_content/

v8.13 will ship: ppt_generator + magazine_generator + whitepaper_generator
v8.14 will ship: admin/systems-view UI surface
v8.15 (optional): G110 audit gate locking the discipline as invariant
"""
from scripts.docgen._registry_loader import load_registry
from scripts.docgen._claim_validator import (
    Claim, validate_claim, validate_claims, ClaimValidationError,
)

__all__ = [
    "load_registry",
    "Claim", "validate_claim", "validate_claims", "ClaimValidationError",
]
