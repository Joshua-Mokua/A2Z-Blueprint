"""scripts/docgen/_claim_validator.py — audit-locked claim verification (v8.12).

Per `docs/A2Z_LIVING_DOCS_PLAN.md` Part 3, every numeric or factual claim
in rendered collateral must trace to the registry dict. If a claim
diverges from reality, generation aborts. The collateral is never written.

This is the documentation analog of our 109 audit gates: collateral is
just code, and code that lies about reality fails the build.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


class ClaimValidationError(Exception):
    """Raised when a claim cannot be verified against the registry."""


# ════════════════════════════════════════════════════════════════════
# Claim dataclass
# ════════════════════════════════════════════════════════════════════

@dataclass
class Claim:
    """A claim made in rendered collateral that must trace to the registry.

    Attributes:
        text: human-readable claim (e.g. "15 of 15 feedback loops wired")
        registry_path: dot-separated path into the registry dict
                       (e.g. "loops_wired" or "platform.audit_gates")
        expected_value: the value the collateral asserts; validator checks
                        registry_path resolves to this exact value
        source_file: human-readable source file name for traceability
                     (e.g. "utils/system_flows.py")
        tolerance: optional numeric tolerance for floating-point claims
                   (use None for strict equality)
    """
    text: str
    registry_path: str
    expected_value: Any
    source_file: str = ""
    tolerance: Optional[float] = None


# ════════════════════════════════════════════════════════════════════
# Path resolver — walks a dot-separated path through nested dicts
# ════════════════════════════════════════════════════════════════════

def _resolve_path(registry: Dict[str, Any], path: str) -> Any:
    """Walk dot-separated path through the registry dict.

    Returns the resolved value. Raises KeyError on missing segments.
    """
    parts = path.split(".")
    cur: Any = registry
    for part in parts:
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(
                    f"path '{path}' missing segment '{part}' "
                    f"(available: {sorted(cur.keys())[:10]}...)")
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                idx = int(part)
                cur = cur[idx]
            except (ValueError, IndexError):
                raise KeyError(
                    f"path '{path}' segment '{part}' is not a valid list index")
        else:
            raise KeyError(
                f"path '{path}' segment '{part}' on non-traversable {type(cur).__name__}")
    return cur


# ════════════════════════════════════════════════════════════════════
# Single-claim validation
# ════════════════════════════════════════════════════════════════════

def validate_claim(claim: Claim, registry: Dict[str, Any]) -> bool:
    """Verify a claim against the registry.

    Returns True if claim matches. Raises ClaimValidationError if it doesn't.
    """
    try:
        actual = _resolve_path(registry, claim.registry_path)
    except KeyError as e:
        raise ClaimValidationError(
            f"Claim '{claim.text}' cannot be verified: registry path "
            f"'{claim.registry_path}' not found ({e})") from e

    expected = claim.expected_value

    # Numeric tolerance (for floating-point comparisons)
    if claim.tolerance is not None and isinstance(expected, (int, float)) \
            and isinstance(actual, (int, float)):
        if abs(actual - expected) > claim.tolerance:
            raise ClaimValidationError(
                f"Claim '{claim.text}' diverges: expected {expected} "
                f"(±{claim.tolerance}), registry says {actual} "
                f"(source: {claim.source_file or claim.registry_path})")
        return True

    # Strict equality
    if actual != expected:
        raise ClaimValidationError(
            f"Claim '{claim.text}' diverges: expected {expected!r}, "
            f"registry says {actual!r} "
            f"(source: {claim.source_file or claim.registry_path})")
    return True


# ════════════════════════════════════════════════════════════════════
# Batch validation
# ════════════════════════════════════════════════════════════════════

def validate_claims(claims: List[Claim], registry: Dict[str, Any],
                     fail_fast: bool = False) -> Dict[str, Any]:
    """Validate multiple claims. Returns summary dict.

    Args:
        claims: list of Claim objects to validate
        registry: the registry dict from load_registry()
        fail_fast: if True, raise on first failure; if False, collect all

    Returns:
        {
            "total": N,
            "passed": K,
            "failed": M,
            "failures": [list of (claim, error_message)],
        }

    Raises:
        ClaimValidationError if fail_fast=True and any claim fails.
    """
    total = len(claims)
    passed = 0
    failures: List[Dict[str, Any]] = []

    for claim in claims:
        try:
            validate_claim(claim, registry)
            passed += 1
        except ClaimValidationError as e:
            if fail_fast:
                raise
            failures.append({
                "claim_text": claim.text,
                "registry_path": claim.registry_path,
                "expected": claim.expected_value,
                "error": str(e),
            })

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "failures": failures,
    }


# ════════════════════════════════════════════════════════════════════
# Self-test — covers the canonical claims from Part 6 of the plan
# ════════════════════════════════════════════════════════════════════

def self_test() -> bool:
    """Round-trip the loader + validator on the canonical Part 6 claims."""
    from scripts.docgen._registry_loader import load_registry
    registry = load_registry()

    # The canonical claims from docs/A2Z_LIVING_DOCS_PLAN.md Part 6
    canonical_claims = [
        Claim(text="6 system stocks",
              registry_path="stocks_count",
              expected_value=6,
              source_file="utils/system_stocks.py"),
        Claim(text="6 of 6 stocks WIRED (100%)",
              registry_path="stocks_wired",
              expected_value=6,
              source_file="utils/system_stocks.py"),
        Claim(text="15 feedback loops",
              registry_path="loops_count",
              expected_value=15,
              source_file="utils/system_flows.py"),
        Claim(text="15 of 15 loops WIRED (100%)",
              registry_path="loops_wired",
              expected_value=15,
              source_file="utils/system_flows.py"),
        Claim(text="100% loops wired",
              registry_path="loops_wired_pct",
              expected_value=100.0,
              source_file="utils/system_flows.py"),
        Claim(text="3 learning loops (L01, L02, L08)",
              registry_path="learning_loops_count",
              expected_value=3,
              source_file="utils/system_flows.py"),
    ]

    result = validate_claims(canonical_claims, registry, fail_fast=False)
    if result["failed"] > 0:
        print(f"FAIL: {result['failed']} claim(s) diverged:")
        for f in result["failures"]:
            print(f"  - {f['claim_text']}: {f['error']}")
        return False

    # Test 2: divergent claim should fail
    bad_claim = Claim(
        text="100 system stocks (deliberately wrong)",
        registry_path="stocks_count",
        expected_value=100,
        source_file="utils/system_stocks.py")
    try:
        validate_claim(bad_claim, registry)
        print("FAIL: bad claim should have raised")
        return False
    except ClaimValidationError:
        pass  # expected

    # Test 3: missing path should fail
    missing_claim = Claim(
        text="nonexistent metric",
        registry_path="this.does.not.exist",
        expected_value=42,
        source_file="nowhere")
    try:
        validate_claim(missing_claim, registry)
        print("FAIL: missing path should have raised")
        return False
    except ClaimValidationError:
        pass  # expected

    return True


if __name__ == "__main__":
    print("A2Z Living Documentation — claim validator self-test")
    ok = self_test()
    print(f"Result: {'PASS' if ok else 'FAIL'}")
